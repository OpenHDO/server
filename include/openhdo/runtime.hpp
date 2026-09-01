#pragma once

#include <string>
#include <string_view>

namespace openhdo {

struct RuntimeInfo {
    std::string_view product;
    std::string_view version;
    std::string_view protocol;
};

[[nodiscard]] RuntimeInfo runtime_info() noexcept;
[[nodiscard]] std::string runtime_description(std::string_view executable);
int run_command_line(std::string_view executable, int argc, char* argv[]);

}  // namespace openhdo
