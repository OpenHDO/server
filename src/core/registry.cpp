#include <openhdo/registry.hpp>

#include <algorithm>

namespace openhdo {

RegistryMutation DeviceRegistry::register_device(Device device) {
    const auto key = std::string(device.id().value());
    if (devices_.contains(key)) {
        return RegistryError{.code = RegistryErrorCode::duplicate_device,
                             .message = "device is already registered"};
    }
    devices_.emplace(key, std::move(device));
    return std::monostate{};
}

DeviceStateResult DeviceRegistry::set_state(const DeviceId& id, const DeviceState state) {
    const auto found = devices_.find(std::string(id.value()));
    if (found == devices_.end()) {
        return RegistryError{.code = RegistryErrorCode::device_not_found,
                             .message = "device is not registered"};
    }
    found->second = found->second.with_state(state);
    return found->second;
}

std::optional<Device> DeviceRegistry::find(const DeviceId& id) const {
    const auto found = devices_.find(std::string(id.value()));
    if (found == devices_.end()) {
        return std::nullopt;
    }
    return found->second;
}

std::vector<Device> DeviceRegistry::list() const {
    std::vector<Device> devices;
    devices.reserve(devices_.size());
    for (const auto& [_, device] : devices_) {
        devices.push_back(device);
    }
    std::sort(devices.begin(), devices.end(), [](const Device& left, const Device& right) {
        return left.id().value() < right.id().value();
    });
    return devices;
}

}  // namespace openhdo
