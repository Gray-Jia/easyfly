// filter_core 单元测试: 距离滤波 + 体素降采样
#include <gtest/gtest.h>
#include <cmath>
#include <vector>

#include "easyfly_pointcloud_filter/filter_core.hpp"

using easyfly_pointcloud_filter::Pt;
using easyfly_pointcloud_filter::rangeFilter;
using easyfly_pointcloud_filter::voxelDownsample;
using easyfly_pointcloud_filter::filterCloud;

TEST(RangeFilter, KeepsPointsInRange)
{
    std::vector<Pt> in = {
        {0.1f, 0, 0, 0},     // 盲区内 (0.1 < 0.3) → 剔除
        {1.0f, 0, 0, 10},    // 1m → 保留
        {0, 0, 5.0f, 20},    // 5m → 保留
        {30.0f, 0, 0, 0},    // 超远界 → 剔除
        {0.31f, 0, 0, 5},    // 恰好在 min 边界 → 保留
    };
    auto out = rangeFilter(in, 0.3f, 25.0f);
    ASSERT_EQ(out.size(), 3u);
    EXPECT_FLOAT_EQ(out[0].x, 1.0f);
    EXPECT_FLOAT_EQ(out[1].z, 5.0f);
    EXPECT_FLOAT_EQ(out[2].x, 0.31f);
}

TEST(RangeFilter, EmptyInput)
{
    EXPECT_TRUE(rangeFilter({}, 0.3f, 25.0f).empty());
}

TEST(VoxelDownsample, MergesPointsInSameVoxel)
{
    // 体素 1.0m: (0.1,0,0) 与 (0.2,0,0) 同体素 → 只留 1 个;
    // (1.5,0,0) 在 x=1 体素 → 共 2 个输出
    std::vector<Pt> in = {{0.1f, 0, 0, 1}, {0.2f, 0, 0, 2}, {1.5f, 0, 0, 3}};
    auto out = voxelDownsample(in, 1.0f);
    EXPECT_EQ(out.size(), 2u);
    // first-wins: 同体素保留先到的 (intensity=1)
    bool has_first = false;
    for (const auto & p : out)
        if (p.intensity == 1.0f) has_first = true;
    EXPECT_TRUE(has_first);
}

TEST(VoxelDownsample, NonPositiveSizeIsNoop)
{
    std::vector<Pt> in = {{0, 0, 0, 0}, {1, 1, 1, 1}};
    EXPECT_EQ(voxelDownsample(in, 0.0f).size(), 2u);
    EXPECT_EQ(voxelDownsample(in, -1.0f).size(), 2u);
}

TEST(FilterChain, ReducesSyntheticCloud)
{
    // 10000 个 0~10m 随机点, 体素 0.5m → 输出应远小于输入且非零
    std::vector<Pt> in;
    in.reserve(10000);
    for (int i = 0; i < 10000; ++i) {
        const float f = static_cast<float>(i) * 0.001f;
        in.push_back({10.0f * std::sin(f * 12.9898f),
                      10.0f * std::sin(f * 78.233f),
                      5.0f * std::sin(f * 37.719f), static_cast<float>(i % 255)});
    }
    auto out = filterCloud(in, 0.5f, 9.0f, 0.5f);
    EXPECT_GT(out.size(), 100u);
    EXPECT_LT(out.size(), in.size() / 2u);
}
