// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstddef>
#include <cstring>

namespace rig_auth {
inline bool valid_token(const char* token) {
    if (!token) return false;
    const std::size_t length = std::strlen(token);
    if (length < 32 || length > 128 || std::strncmp(token, "GENERATE_", 9) == 0) return false;
    for (std::size_t i = 0; i < length; ++i) {
        const unsigned char c = token[i];
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
              (c >= '0' && c <= '9') || c == '_' || c == '-')) return false;
    }
    return true;
}

// Strict single-space Bearer syntax. Token comparison does not exit early.
inline bool authorized(const char* header, const char* token) {
    if (!header || !valid_token(token)) return false;
    const std::size_t token_length = std::strlen(token);
    if (std::strlen(header) != token_length + 7) return false;
    const char* scheme = "bearer ";
    for (std::size_t i = 0; i < 7; ++i) {
        unsigned char c = header[i];
        if (c >= 'A' && c <= 'Z') c = c - 'A' + 'a';
        if (c != static_cast<unsigned char>(scheme[i])) return false;
    }
    unsigned char difference = 0;
    for (std::size_t i = 0; i < token_length; ++i)
        difference |= static_cast<unsigned char>(header[i + 7]) ^ static_cast<unsigned char>(token[i]);
    return difference == 0;
}
}  // namespace rig_auth
