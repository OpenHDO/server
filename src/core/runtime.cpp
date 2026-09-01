#include <openhdo/config.hpp>
#include <openhdo/runtime.hpp>

#include <iostream>
#include <string>

namespace openhdo {

RuntimeInfo runtime_info() noexcept {
    return {.product = "OpenHDO", .version = OPENHDO_VERSION, .protocol = "1"};
}

std::string runtime_description(const std::string_view executable) {
    const auto info = runtime_info();
    return std::string(executable) + " " + std::string(info.version) + " (protocol v" +
           std::string(info.protocol) + ")";
}

int run_command_line(const std::string_view executable, const int argc, char* argv[]) {
    if (argc > 1) {
        const std::string_view argument{argv[1]};
        if (argument == "--version" || argument == "-V") {
            std::cout << runtime_description(executable) << '\n';
            return 0;
        }
        if (argument == "--check") {
            std::cout << "ok " << runtime_description(executable) << '\n';
            return 0;
        }
        if (argument != "--help" && argument != "-h") {
            std::cerr << "unknown option: " << argument << '\n';
            return 2;
        }
    }

    std::cout << runtime_description(executable) << '\n'
              << "foundation runtime: ready\n"
              << "usage: " << executable << " [--check|--version|--help]\n";
    return 0;
}

}  // namespace openhdo
