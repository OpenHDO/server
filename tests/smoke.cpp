#include <openhdo/runtime.hpp>

#include <string>

int main() {
    const auto info = openhdo::runtime_info();
    if (info.product != "OpenHDO" || info.version.empty() || info.protocol != "1") {
        return 1;
    }
    if (openhdo::runtime_description("test").find("protocol v1") == std::string::npos) {
        return 1;
    }
    return 0;
}
