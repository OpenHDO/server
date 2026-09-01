#pragma once

#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>

namespace openhdo {

enum class DomainErrorCode {
    invalid_id,
    invalid_name,
    invalid_capability,
};

struct DomainError {
    DomainErrorCode code;
    std::string message;
};

class DeviceId {
public:
    [[nodiscard]] static std::variant<DeviceId, DomainError> create(std::string_view value);

    [[nodiscard]] std::string_view value() const noexcept { return value_; }

    friend bool operator==(const DeviceId&, const DeviceId&) = default;

private:
    explicit DeviceId(std::string value) : value_(std::move(value)) {}

    std::string value_;
};

enum class DeviceState {
    offline,
    online,
};

[[nodiscard]] std::string_view device_state_name(DeviceState state) noexcept;

class Device {
public:
    [[nodiscard]] static std::variant<Device, DomainError> create(
        std::string_view id, std::string_view display_name,
        std::vector<std::string> capabilities, DeviceState state = DeviceState::offline);

    [[nodiscard]] const DeviceId& id() const noexcept { return id_; }
    [[nodiscard]] std::string_view display_name() const noexcept { return display_name_; }
    [[nodiscard]] const std::vector<std::string>& capabilities() const noexcept {
        return capabilities_;
    }
    [[nodiscard]] DeviceState state() const noexcept { return state_; }

    [[nodiscard]] Device with_state(DeviceState state) const;

private:
    Device(DeviceId id, std::string display_name, std::vector<std::string> capabilities,
           DeviceState state)
        : id_(std::move(id)),
          display_name_(std::move(display_name)),
          capabilities_(std::move(capabilities)),
          state_(state) {}

    DeviceId id_;
    std::string display_name_;
    std::vector<std::string> capabilities_;
    DeviceState state_;
};

}  // namespace openhdo
