# Copyright 2026 EasyFly Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pure geometry with original XYZ preserved and nearest-depth occlusion."""
import math
import struct


def camera_model(info):
    if (
        not 0 < info.width <= 2048
        or not 0 < info.height <= 2048
        or info.width * info.height > 1048576
    ):
        raise ValueError('camera pixel budget')
    if info.distortion_model != 'plumb_bob' or len(info.d) != 5:
        raise ValueError('only plumb_bob/5 supported')
    if (
        not all(math.isfinite(v) for v in (*info.k, *info.d))
        or info.k[0] <= 0
        or info.k[4] <= 0
    ):
        raise ValueError('invalid intrinsics')
    if (
        info.k[0] > 100000
        or info.k[4] > 100000
        or not 0 <= info.k[2] <= info.width
        or not 0 <= info.k[5] <= info.height
    ):
        raise ValueError('intrinsic range')
    if (
        any(abs(info.k[i]) > 1e-9 for i in (1, 3, 6, 7))
        or abs(info.k[8] - 1) > 1e-9
    ):
        raise ValueError('invalid K form')
    if any(abs(v) > 100 for v in info.d):
        raise ValueError('distortion range')
    return (info.width, info.height, tuple(info.k), tuple(info.d))


def image_layout(image):
    channels = {'mono8': 1, 'rgb8': 3, 'bgr8': 3}.get(image.encoding)
    if (
        not channels
        or not 0 < image.width <= 2048
        or not 0 < image.height <= 2048
    ):
        raise ValueError('image encoding/dimensions')
    if image.width * image.height > 1048576 or len(image.data) > 4194304:
        raise ValueError('image budget')
    if (
        image.step < image.width * channels
        or len(image.data) != image.step * image.height
    ):
        raise ValueError('image byte layout')
    return channels


def cloud_points(cloud, max_points):
    count = cloud.width * cloud.height
    if (
        count > max_points
        or cloud.point_step < 1
        or cloud.point_step > 256
        or len(cloud.data) > 8388608
    ):
        raise ValueError('cloud budget')
    if (
        cloud.row_step < cloud.width * cloud.point_step
        or len(cloud.data) != cloud.row_step * cloud.height
    ):
        raise ValueError('cloud layout')
    if len(cloud.fields) > 32:
        raise ValueError('cloud fields budget')
    fields = {}
    for field in cloud.fields:
        if field.name in ('x', 'y', 'z'):
            if (
                field.name in fields
                or field.count != 1
                or field.datatype not in (7, 8)
            ):
                raise ValueError('XYZ field type/duplicate')
            size = 4 if field.datatype == 7 else 8
            if field.offset < 0 or field.offset + size > cloud.point_step:
                raise ValueError('XYZ offset')
            fields[field.name] = (
                field.offset,
                size,
                'f' if size == 4 else 'd',
            )
    if set(fields) != {'x', 'y', 'z'}:
        raise ValueError('XYZ missing')
    ordered = sorted((o, o + size) for o, size, _ in fields.values())
    if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('overlapping XYZ')
    endian = '>' if cloud.is_bigendian else '<'
    points = []
    for row in range(cloud.height):
        for column in range(cloud.width):
            start = row * cloud.row_step + column * cloud.point_step
            point = tuple(
                struct.unpack_from(
                    endian + fields[key][2], cloud.data, start + fields[key][0]
                )[0]
                for key in ('x', 'y', 'z')
            )
            if all(math.isfinite(v) and abs(v) <= 100000 for v in point):
                points.append(point)
    return points


def rigid_transform(transform):
    q = transform.rotation
    t = transform.translation
    values = (q.x, q.y, q.z, q.w, t.x, t.y, t.z)
    if not all(math.isfinite(v) for v in values):
        raise ValueError('invalid TF')
    norm = math.sqrt(sum(v * v for v in values[:4]))
    if abs(norm - 1) > 0.001:
        raise ValueError('TF quaternion not normalized')
    x, y, z, w = (v / norm for v in values[:4])
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    ), values[4:]


def project(points, image, model, transform):
    channels = image_layout(image)
    width, height, k, d = model
    if (image.width, image.height) != (width, height):
        raise ValueError('image/intrinsic resolution mismatch')
    rotation, translation = rigid_transform(transform)
    nearest = {}
    for original in points:
        x, y, z = (
            sum(rotation[row][axis] * original[axis] for axis in range(3))
            + translation[row]
            for row in range(3)
        )
        if not math.isfinite(z) or z <= 0.000001:
            continue
        x, y = x / z, y / z
        r2 = x * x + y * y
        radial = 1 + d[0] * r2 + d[1] * r2 * r2 + d[4] * r2 * r2 * r2
        xd = x * radial + 2 * d[2] * x * y + d[3] * (r2 + 2 * x * x)
        yd = y * radial + d[2] * (r2 + 2 * y * y) + 2 * d[3] * x * y
        u, v = k[0] * xd + k[2], k[4] * yd + k[5]
        if (
            not math.isfinite(u)
            or not math.isfinite(v)
            or not -0.5 <= u < width - 0.5
            or not -0.5 <= v < height - 0.5
        ):
            continue
        pixel = (int(math.floor(u + 0.5)), int(math.floor(v + 0.5)))
        if pixel not in nearest or z < nearest[pixel][0]:
            nearest[pixel] = (z, original)
    depth = [float('nan')] * (width * height)
    colored = bytearray()
    for (u, v), (z, original) in nearest.items():
        start = v * image.step + u * channels
        if channels == 1:
            r = g = b = image.data[start]
        else:
            end = start + 3
            r, g, b = image.data[start:end]
            if image.encoding == 'bgr8':
                r, b = b, r
        depth[v * width + u] = z
        colored.extend(
            struct.pack('<fffI', *original, (r << 16) | (g << 8) | b)
        )
    return (
        bytes(colored),
        struct.pack('<' + 'f' * len(depth), *depth),
        len(nearest),
    )
