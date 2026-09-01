#pragma once

#include <optional>
#include <string>
#include <unordered_map>
#include <variant>
#include <vector>

#include <openhdo/domain.hpp>

namespace openhdo {

enum class RegistryErrorCode {
    duplicate_device,
    device_not_found,
};

struct RegistryError {
    RegistryErrorCode code;
    std::string message;
};

using RegistryMutation = std::variant<std::monostate, RegistryError>;
using DeviceStateResult = std::variant<Device, RegistryError>;

class DeviceRegistry {
public:
    [[nodiscard]] RegistryMutation register_device(Device device);
    [[nodiscard]] DeviceStateResult set_state(const DeviceId& id, DeviceState state);

    [[nodiscard]] std::optional<Device> find(const DeviceId& id) const;
    [[nodiscard]] std::vector<Device> list() const;

private:
    std::unordered_map<std::string, Device> devices_;
};

}  // namespace openhdo
