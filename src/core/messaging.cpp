#include <openhdo/messaging.hpp>

#include <string>
#include <type_traits>

namespace openhdo {

std::string message_id_string(const MessageId id) { return std::to_string(id.value()); }

std::optional<MessageError> validate(const CommandMessage& message) {
    if (message.version != CommandMessage::kVersion) {
        return MessageError{.code = MessageErrorCode::unsupported_version,
                            .message = "unsupported command message version"};
    }
    if (message.id.value() == 0 || message.correlation_id.value() == 0) {
        return MessageError{.code = MessageErrorCode::invalid_id,
                            .message = "command id and correlation id must be non-zero"};
    }
    return std::nullopt;
}

std::optional<MessageError> validate(const EventMessage& message) {
    if (message.version != EventMessage::kVersion) {
        return MessageError{.code = MessageErrorCode::unsupported_version,
                            .message = "unsupported event message version"};
    }
    if (message.id.value() == 0 || message.correlation_id.value() == 0) {
        return MessageError{.code = MessageErrorCode::invalid_id,
                            .message = "event id and correlation id must be non-zero"};
    }
    return std::nullopt;
}

std::string_view command_type(const Command& command) noexcept {
    return std::visit(
        [](const auto& value) -> std::string_view {
            using T = std::decay_t<decltype(value)>;
            if constexpr (std::is_same_v<T, RegisterDeviceCommand>) {
                return "device.register";
            } else {
                return "device.set_state";
            }
        },
        command);
}

std::string_view event_type(const Event& event) noexcept {
    return std::visit(
        [](const auto& value) -> std::string_view {
            using T = std::decay_t<decltype(value)>;
            if constexpr (std::is_same_v<T, DeviceRegisteredEvent>) {
                return "device.registered";
            } else {
                return "device.state_changed";
            }
        },
        event);
}

}  // namespace openhdo
