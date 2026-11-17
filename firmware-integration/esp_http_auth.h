// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <esp_http_server.h>
#include "bearer_auth.h"

namespace rig_auth {
// Invoke before reading the body, parsing RPC, or dispatching any action.
inline bool http_authorized(httpd_req_t* request, const char* token) {
    const std::size_t length = httpd_req_get_hdr_value_len(request, "Authorization");
    char value[136] = {};
    return length > 0 && length < sizeof(value) &&
           httpd_req_get_hdr_value_str(request, "Authorization", value, sizeof(value)) == ESP_OK &&
           authorized(value, token);
}
}  // namespace rig_auth
