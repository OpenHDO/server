#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <utility>
#include <variant>
#include <vector>

#include <openhdo/logging.hpp>
#include <openhdo/messaging.hpp>
#include <openhdo/registry.hpp>

namespace openhdo {

enum class DispatchErrorCode {
    invalid_message,
    duplicate_device,
    device_not_found,
};

struct DispatchError {
    DispatchErrorCode code;
    std::string message;
};

struct DispatchSuccess {
    MessageId correlation_id;
    std::vector<EventMessage> events;
};

struct DispatchFailure {
    MessageId correlation_id;
    DispatchError error;
};

using DispatchResult = std::variant<DispatchSuccess, DispatchFailure>;

class ControlPlane {
public:
    using SubscriptionId = std::uint64_t;
    using EventHandler = std::function<void(const EventMessage&)>;

    explicit ControlPlane(Logger& logger) : logger_(logger) {}

    [[nodiscard]] DispatchResult dispatch(const CommandMessage& command);
    [[nodiscard]] SubscriptionId subscribe(EventHandler handler);
    [[nodiscard]] bool unsubscribe(SubscriptionId id);

    [[nodiscard]] const DeviceRegistry& registry() const noexcept { return registry_; }

private:
    [[nodiscard]] DispatchResult reject(const CommandMessage& command, DispatchErrorCode code,
                                        std::string message);
    void publish(const EventMessage& event);

    Logger& logger_;
    DeviceRegistry registry_;
    MessageIdGenerator event_ids_;
    SubscriptionId next_subscription_id_{1};
    std::vector<std::pair<SubscriptionId, EventHandler>> subscribers_;
};

}  // namespace openhdo
