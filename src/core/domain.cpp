#include <openhdo/domain.hpp>

#include <utility>

namespace openhdo {
namespace {

[[nodiscard]] bool valid_identifier(const std::string_view value) noexcept {
    if (value.empty() || value.size() > 128) {
        return false;
    }
    const char first = value.front();
    if (first < 'a' || first > 'z') {
        return false;
    }
    for (const char character : value) {
        const bool alphanumeric =
            (character >= 'a' && character <= 'z') || (character >= '0' && character <= '9');
        if (!alphanumeric && character != '.' && character != '_' && character != '-') {
            return false;
        }
    }
    return true;
}

[[nodiscard]] bool valid_display_name(const std::string_view value) noexcept {
    if (value.empty() || value.size() > 128) {
        return false;
    }
    for (const char character : value) {
        if (character != ' ' && character != '\t' && character != '\n' && character != '\r') {
            return true;
        }
    }
    return false;
}

}  // namespace

std::variant<DeviceId, DomainError> DeviceId::create(const std::string_view value) {
    if (!valid_identifier(value)) {
        return DomainError{.code = DomainErrorCode::invalid_id,
                           .message = "device id must be 1-128 lowercase identifier characters"};
    }
    return DeviceId{std::string(value)};
}

std::string_view device_state_name(const DeviceState state) noexcept {
    switch (state) {
        case DeviceState::offline:
            return "offline";
        case DeviceState::online:
            return "online";
    }
    return "unknown";
}

std::variant<Device, DomainError> Device::create(const std::string_view id,
                                                 const std::string_view display_name,
                                                 std::vector<std::string> capabilities,
                                                 const DeviceState state) {
    auto parsed_id = DeviceId::create(id);
    if (auto* error = std::get_if<DomainError>(&parsed_id); error != nullptr) {
        return *error;
    }
    if (!valid_display_name(display_name)) {
        return DomainError{.code = DomainErrorCode::invalid_name,
                           .message = "device display name must be 1-128 non-whitespace characters"};
    }
    for (const auto& capability : capabilities) {
        if (!valid_identifier(capability) || capability.size() > 64) {
            return DomainError{.code = DomainErrorCode::invalid_capability,
                               .message = "capabilities must be lowercase identifier characters"};
        }
    }

    return Device{std::get<DeviceId>(std::move(parsed_id)), std::string(display_name),
                  std::move(capabilities), state};
}

Device Device::with_state(const DeviceState state) const {
    return Device{id_, display_name_, capabilities_, state};
}

}  // namespace openhdo
