#include "bearer_auth.h"
#include <cassert>
#include <string>

int main() {
    const std::string token(43, 'a');
    assert(rig_auth::authorized(("Bearer " + token).c_str(), token.c_str()));
    assert(rig_auth::authorized(("bEaReR " + token).c_str(), token.c_str()));
    for (const auto& header : {std::string(), "Basic " + token, "Bearer  " + token,
                              "Bearer " + token + " ", "Bearer " + token.substr(1)})
        assert(!rig_auth::authorized(header.c_str(), token.c_str()));
    for (std::size_t i = 0; i < token.size(); ++i) {
        std::string bad = token; bad[i] = 'b';
        assert(!rig_auth::authorized(("Bearer " + bad).c_str(), token.c_str()));
    }
    assert(!rig_auth::authorized(nullptr, token.c_str()));
    assert(!rig_auth::authorized("Bearer ", ""));
    assert(!rig_auth::valid_token("GENERATE_WITH_SCRIPTS_CONFIGURE_PY"));
    assert(!rig_auth::valid_token(std::string(129, 'x').c_str()));
    assert(!rig_auth::valid_token((token + "\n").c_str()));
    const std::string longest(128, 'z');
    assert(rig_auth::authorized(("Bearer " + longest).c_str(), longest.c_str()));
}
