#pragma once

#include <map>
#include <string>
#include <variant>

#include <openhdo/logging.hpp>

namespace openhdo {

struct Configuration {
    static constexpr int kVersion = 1;

    std::string instance_name;
    LogLevel log_level;
};

enum class ConfigurationErrorCode {
    unsupported_version,
    invalid_value,
};

struct ConfigurationError {
    ConfigurationErrorCode code;
    std::string key;
    std::string message;
};

using ConfigurationValues = std::map<std::string, std::string>;
using ConfigurationResult = std::variant<Configuration, ConfigurationError>;

// The map is the narrow boundary for file, environment, or CLI adapters.
// Unknown keys are ignored so adding optional settings remains compatible.
[[nodiscard]] ConfigurationResult load_configuration(const ConfigurationValues& values);

// Reads only OPENHDO_* settings. Parsing and validation remain in
// load_configuration so tests and future config-file adapters use the same path.
[[nodiscard]] ConfigurationValues configuration_from_environment();

}  // namespace openhdo
