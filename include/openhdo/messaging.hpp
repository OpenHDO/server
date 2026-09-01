#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <variant>

#include <openhdo/domain.hpp>

namespace openhdo {

class MessageId {
public:
    constexpr explicit MessageId(std::uint64_t value = 0) noexcept : value_(value) {}

    [[nodiscard]] constexpr std::uint64_t value() const noexcept { return value_; }

    friend constexpr bool operator==(const MessageId&, const MessageId&) = default;

private:
    std::uint64_t value_;
};

class MessageIdGenerator {
public:
    [[nodiscard]] MessageId next() noexcept { return MessageId{next_++}; }

private:
    std::uint64_t next_{1};
};

[[nodiscard]] std::string message_id_string(MessageId id);

struct RegisterDeviceCommand {
    Device device;
};

struct SetDeviceStateCommand {
    DeviceId device_id;
    DeviceState state;
};

using Command = std::variant<RegisterDeviceCommand, SetDeviceStateCommand>;

struct CommandMessage {
    static constexpr std::uint16_t kVersion = 1;

    std::uint16_t version;
    MessageId id;
    MessageId correlation_id;
    Command payload;
};

enum class MessageErrorCode {
    unsupported_version,
    invalid_id,
};

struct MessageError {
    MessageErrorCode code;
    std::string message;
};

[[nodiscard]] std::optional<MessageError> validate(const CommandMessage& message);
[[nodiscard]] std::string_view command_type(const Command& command) noexcept;

struct DeviceRegisteredEvent {
    Device device;
};

struct DeviceStateChangedEvent {
    DeviceId device_id;
    DeviceState previous_state;
    DeviceState state;
};

using Event = std::variant<DeviceRegisteredEvent, DeviceStateChangedEvent>;

struct EventMessage {
    static constexpr std::uint16_t kVersion = 1;

    std::uint16_t version;
    MessageId id;
    MessageId correlation_id;
    Event payload;
};

[[nodiscard]] std::optional<MessageError> validate(const EventMessage& message);
[[nodiscard]] std::string_view event_type(const Event& event) noexcept;

}  // namespace openhdo
