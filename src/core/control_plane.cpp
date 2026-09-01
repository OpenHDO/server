#include <openhdo/control_plane.hpp>

#include <algorithm>
#include <exception>
#include <string>
#include <type_traits>
#include <utility>

namespace openhdo {

DispatchResult ControlPlane::dispatch(const CommandMessage& command) {
    if (const auto message_error = validate(command); message_error.has_value()) {
        return reject(command, DispatchErrorCode::invalid_message, message_error->message);
    }

    return std::visit(
        [this, &command](const auto& payload) -> DispatchResult {
            using T = std::decay_t<decltype(payload)>;
            if constexpr (std::is_same_v<T, RegisterDeviceCommand>) {
                const auto registration = registry_.register_device(payload.device);
                if (const auto* error = std::get_if<RegistryError>(&registration);
                    error != nullptr) {
                    return reject(command, DispatchErrorCode::duplicate_device, error->message);
                }

                EventMessage event{.version = EventMessage::kVersion,
                                   .id = event_ids_.next(),
                                   .correlation_id = command.correlation_id,
                                   .payload = DeviceRegisteredEvent{.device = payload.device}};
                publish(event);
                logger_.info("control-plane", "command.accepted",
                             {{"command_type", std::string(command_type(command.payload))},
                              {"correlation_id", message_id_string(command.correlation_id)},
                              {"event_type", std::string(event_type(event.payload))}});
                return DispatchSuccess{.correlation_id = command.correlation_id,
                                       .events = {std::move(event)}};
            } else {
                const auto current = registry_.find(payload.device_id);
                if (!current.has_value()) {
                    return reject(command, DispatchErrorCode::device_not_found,
                                  "device is not registered");
                }

                const auto updated = registry_.set_state(payload.device_id, payload.state);
                if (const auto* error = std::get_if<RegistryError>(&updated); error != nullptr) {
                    return reject(command, DispatchErrorCode::device_not_found, error->message);
                }
                if (current->state() == payload.state) {
                    logger_.debug("control-plane", "command.accepted.noop",
                                  {{"command_type", std::string(command_type(command.payload))},
                                   {"correlation_id", message_id_string(command.correlation_id)}});
                    return DispatchSuccess{.correlation_id = command.correlation_id, .events = {}};
                }

                EventMessage event{
                    .version = EventMessage::kVersion,
                    .id = event_ids_.next(),
                    .correlation_id = command.correlation_id,
                    .payload = DeviceStateChangedEvent{.device_id = payload.device_id,
                                                       .previous_state = current->state(),
                                                       .state = payload.state}};
                publish(event);
                logger_.info("control-plane", "command.accepted",
                             {{"command_type", std::string(command_type(command.payload))},
                              {"correlation_id", message_id_string(command.correlation_id)},
                              {"event_type", std::string(event_type(event.payload))}});
                return DispatchSuccess{.correlation_id = command.correlation_id,
                                       .events = {std::move(event)}};
            }
        },
        command.payload);
}

ControlPlane::SubscriptionId ControlPlane::subscribe(EventHandler handler) {
    if (!handler) {
        return 0;
    }
    const auto id = next_subscription_id_++;
    subscribers_.emplace_back(id, std::move(handler));
    return id;
}

bool ControlPlane::unsubscribe(const SubscriptionId id) {
    const auto found = std::find_if(subscribers_.begin(), subscribers_.end(),
                                    [id](const auto& subscriber) { return subscriber.first == id; });
    if (found == subscribers_.end()) {
        return false;
    }
    subscribers_.erase(found);
    return true;
}

DispatchResult ControlPlane::reject(const CommandMessage& command, const DispatchErrorCode code,
                                    std::string message) {
    logger_.warn("control-plane", "command.rejected",
                 {{"command_type", std::string(command_type(command.payload))},
                  {"correlation_id", message_id_string(command.correlation_id)},
                  {"reason", message}});
    return DispatchFailure{.correlation_id = command.correlation_id,
                           .error = {.code = code, .message = std::move(message)}};
}

void ControlPlane::publish(const EventMessage& event) {
    logger_.debug("control-plane", "event.published",
                  {{"event_type", std::string(event_type(event.payload))},
                   {"event_id", message_id_string(event.id)},
                   {"correlation_id", message_id_string(event.correlation_id)}});

    const std::vector<EventHandler> handlers = [&] {
        std::vector<EventHandler> copy;
        copy.reserve(subscribers_.size());
        for (const auto& [_, handler] : subscribers_) {
            copy.push_back(handler);
        }
        return copy;
    }();
    for (const auto& handler : handlers) {
        try {
            handler(event);
        } catch (const std::exception& exception) {
            logger_.error("control-plane", "event.handler_failed",
                          {{"event_type", std::string(event_type(event.payload))},
                           {"error", exception.what()}});
        } catch (...) {
            logger_.error("control-plane", "event.handler_failed",
                          {{"event_type", std::string(event_type(event.payload))},
                           {"error", "unknown exception"}});
        }
    }
}

}  // namespace openhdo
