#include <openhdo/configuration.hpp>

#include <charconv>
#include <cstddef>
#include <cstdlib>
#include <optional>
#include <utility>

namespace openhdo {
namespace {

[[nodiscard]] bool valid_token(const std::string_view value, const std::size_t maximum) noexcept {
    if (value.empty() || value.size() > maximum) {
        return false;
    }
    for (const char character : value) {
        const bool alphanumeric =
            (character >= 'a' && character <= 'z') || (character >= 'A' && character <= 'Z') ||
            (character >= '0' && character <= '9');
        if (!alphanumeric && character != '.' && character != '_' && character != '-') {
            return false;
        }
    }
    return true;
}

[[nodiscard]] ConfigurationError error(const ConfigurationErrorCode code, const std::string& key,
                                       const std::string& message) {
    return {.code = code, .key = key, .message = message};
}

[[nodiscard]] std::optional<std::string> environment_value(const char* name) {
#if defined(_MSC_VER)
    char* value = nullptr;
    std::size_t length = 0;
    if (_dupenv_s(&value, &length, name) != 0 || value == nullptr) {
        return std::nullopt;
    }
    std::string result(value, length == 0 ? 0 : length - 1);
    std::free(value);
    return result;
#else
    if (const char* value = std::getenv(name); value != nullptr) {
        return std::string(value);
    }
    return std::nullopt;
#endif
}

}  // namespace

ConfigurationResult load_configuration(const ConfigurationValues& values) {
    int version = Configuration::kVersion;
    if (const auto found = values.find("config_version"); found != values.end()) {
        const auto* first = found->second.data();
        const auto* last = first + found->second.size();
        const auto parsed = std::from_chars(first, last, version);
        if (parsed.ec != std::errc{} || parsed.ptr != last) {
            return error(ConfigurationErrorCode::invalid_value, found->first,
                         "config_version must be an integer");
        }
    }
    if (version != Configuration::kVersion) {
        return error(ConfigurationErrorCode::unsupported_version, "config_version",
                     "unsupported configuration version");
    }

    std::string instance_name = "openhdo-server";
    if (const auto found = values.find("instance_name"); found != values.end()) {
        instance_name = found->second;
    }
    if (!valid_token(instance_name, 64)) {
        return error(ConfigurationErrorCode::invalid_value, "instance_name",
                     "instance_name must be 1-64 characters using letters, digits, '.', '_' or '-'");
    }

    LogLevel log_level = LogLevel::info;
    if (const auto found = values.find("log_level"); found != values.end()) {
        const auto parsed = parse_log_level(found->second);
        if (!parsed.has_value()) {
            return error(ConfigurationErrorCode::invalid_value, found->first,
                         "log_level must be trace, debug, info, warn, or error");
        }
        log_level = *parsed;
    }

    return Configuration{.instance_name = std::move(instance_name), .log_level = log_level};
}

ConfigurationValues configuration_from_environment() {
    ConfigurationValues values;
    const auto copy_environment = [&values](const char* environment_name,
                                             const char* configuration_name) {
        if (const auto value = environment_value(environment_name); value.has_value()) {
            values.emplace(configuration_name, *value);
        }
    };

    copy_environment("OPENHDO_CONFIG_VERSION", "config_version");
    copy_environment("OPENHDO_INSTANCE_NAME", "instance_name");
    copy_environment("OPENHDO_LOG_LEVEL", "log_level");
    return values;
}

}  // namespace openhdo
