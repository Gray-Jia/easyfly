#ifndef EASYFLY_UTILS_CRC_HPP_
#define EASYFLY_UTILS_CRC_HPP_

#include <cstdint>
#include <cstddef>

namespace easyfly_utils {

inline uint8_t crc8(const uint8_t* data, size_t len) {
  uint8_t crc = 0x00;
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (int j = 0; j < 8; ++j)
      crc = (crc & 0x80) ? ((crc << 1) ^ 0x07) : (crc << 1);
  }
  return crc;
}

}  // namespace easyfly_utils
#endif  // EASYFLY_UTILS_CRC_HPP_
