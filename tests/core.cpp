#include <openhdo/configuration.hpp>
#include <openhdo/control_plane.hpp>
#include <openhdo/domain.hpp>
#include <openhdo/logging.hpp>
#include <openhdo/messaging.hpp>

#include <chrono>
#include <iostream>
#include <sstream>
#include <string>
#include <variant>
#include <vector>

namespace {

int failures = 0;

void check(const bool condition, const char* message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}

openhdo::Device make_device(const std::string_view id) {
    const auto result = openhdo::Device::create(id, "Kitchen light", {"switch"});
    check(std::holds_alternative<openhdo::Device>(result), "valid device is created");
    return std::get<openhdo::Device>(result);
}

void configuration_tests() {
    const auto defaults = openhdo::load_configuration({});
    check(std::holds_alternative<openhdo::Configuration>(defaults), "default configuration loads");
    if (const auto* configuration = std::get_if<openhdo::Configuration>(&defaults);
        configuration != nullptr) {
        check(configuration->instance_name == "openhdo-server", "default instance name is stable");
        check(configuration->log_level == openhdo::LogLevel::info, "default log level is info");
    }

    const auto unsupported = openhdo::load_configuration({{"config_version", "2"}});
    check(std::holds_alternative<openhdo::ConfigurationError>(unsupported),
          "unsupported configuration version is rejected");
    if (const auto* error = std::get_if<openhdo::ConfigurationError>(&unsupported); error != nullptr) {
        check(error->code == openhdo::ConfigurationErrorCode::unsupported_version,
              "configuration error identifies version mismatch");
    }

    const auto invalid_level = openhdo::load_configuration({{"log_level", "verbose"}});
    check(std::holds_alternative<openhdo::ConfigurationError>(invalid_level),
          "unknown log level is rejected");

    const auto invalid_name = openhdo::load_configuration({{"instance_name", "bad/name"}});
    check(std::holds_alternative<openhdo::ConfigurationError>(invalid_name),
          "invalid instance name is rejected");
}

void domain_tests() {
    const auto invalid_id = openhdo::Device::create("Kitchen Light", "Kitchen light", {});
    check(std::holds_alternative<openhdo::DomainError>(invalid_id),
          "device identifiers reject spaces and uppercase characters");

    const auto invalid_name = openhdo::Device::create("kitchen-light", "   ", {});
    check(std::holds_alternative<openhdo::DomainError>(invalid_name),
          "device names reject whitespace-only values");

    const auto invalid_capability =
        openhdo::Device::create("kitchen-light", "Kitchen light", {"Switch"});
    check(std::holds_alternative<openhdo::DomainError>(invalid_capability),
          "capabilities reject non-canonical identifiers");
}

void logging_tests() {
    std::ostringstream output;
    const auto fixed_time = [] {
        return openhdo::Logger::Clock::time_point{std::chrono::milliseconds{0}};
    };
    openhdo::Logger logger(output, openhdo::LogLevel::info, fixed_time);
    logger.debug("test", "ignored");
    logger.info("test\"component", "value\nevent", {{"quoted", "line\nvalue"}});
    check(output.str() ==
              "{\"ts\":\"1970-01-01T00:00:00.000Z\",\"level\":\"info\",\"component\":\"test\\\"component\",\"event\":\"value\\nevent\",\"fields\":{\"quoted\":\"line\\nvalue\"}}\n",
          "logger emits escaped JSON lines and applies the level threshold");
}

void control_plane_tests() {
    std::ostringstream log_output;
    openhdo::Logger logger(log_output, openhdo::LogLevel::debug,
                           [] { return openhdo::Logger::Clock::time_point{}; });
    openhdo::ControlPlane control_plane(logger);
    openhdo::MessageIdGenerator ids;
    std::vector<openhdo::EventMessage> received;
    const auto subscription = control_plane.subscribe(
        [&received](const openhdo::EventMessage& event) { received.push_back(event); });
    check(subscription != 0, "event subscription receives an id");
    check(control_plane.subscribe({}) == 0, "empty event handlers are rejected");

    const auto device = make_device("kitchen-light");
    const openhdo::MessageId register_correlation = ids.next();
    const openhdo::CommandMessage register_command{
        .version = openhdo::CommandMessage::kVersion,
        .id = ids.next(),
        .correlation_id = register_correlation,
        .payload = openhdo::RegisterDeviceCommand{.device = device}};
    const auto registered = control_plane.dispatch(register_command);
    check(std::holds_alternative<openhdo::DispatchSuccess>(registered),
          "register command succeeds");
    if (const auto* success = std::get_if<openhdo::DispatchSuccess>(&registered); success != nullptr) {
        check(success->correlation_id == register_correlation, "reply preserves correlation id");
        check(success->events.size() == 1, "register command emits one event");
        if (!success->events.empty()) {
            check(success->events.front().version == openhdo::EventMessage::kVersion,
                  "event is versioned");
            check(success->events.front().correlation_id == register_correlation,
                  "event preserves correlation id");
            check(openhdo::event_type(success->events.front().payload) == "device.registered",
                  "register event has stable type");
        }
    }
    check(received.size() == 1, "subscribers receive published events");
    check(control_plane.registry().find(device.id()).has_value(), "registry stores registered device");

    const auto second_device = make_device("bedroom-light");
    const openhdo::CommandMessage second_register{
        .version = openhdo::CommandMessage::kVersion,
        .id = ids.next(),
        .correlation_id = ids.next(),
        .payload = openhdo::RegisterDeviceCommand{.device = second_device}};
    check(std::holds_alternative<openhdo::DispatchSuccess>(control_plane.dispatch(second_register)),
          "second registration succeeds");
    const auto devices = control_plane.registry().list();
    check(devices.size() == 2, "registry lists all devices");
    if (devices.size() == 2) {
        check(devices[0].id().value() == "bedroom-light" &&
                  devices[1].id().value() == "kitchen-light",
              "registry list ordering is deterministic");
    }

    const openhdo::MessageId state_correlation = ids.next();
    const openhdo::CommandMessage state_command{
        .version = openhdo::CommandMessage::kVersion,
        .id = ids.next(),
        .correlation_id = state_correlation,
        .payload = openhdo::SetDeviceStateCommand{.device_id = device.id(),
                                                  .state = openhdo::DeviceState::online}};
    const auto state_changed = control_plane.dispatch(state_command);
    check(std::holds_alternative<openhdo::DispatchSuccess>(state_changed),
          "state command succeeds");
    if (const auto* success = std::get_if<openhdo::DispatchSuccess>(&state_changed);
        success != nullptr) {
        check(success->events.size() == 1, "state change emits one event");
        if (!success->events.empty()) {
            const auto* event = std::get_if<openhdo::DeviceStateChangedEvent>(
                &success->events.front().payload);
            check(event != nullptr, "state change event is typed");
            if (event != nullptr) {
                check(event->previous_state == openhdo::DeviceState::offline,
                      "state event records previous state");
                check(event->state == openhdo::DeviceState::online,
                      "state event records new state");
            }
        }
        if (!success->events.empty()) {
            check(!openhdo::validate(success->events.front()).has_value(),
                  "published event passes envelope validation");
        }
    }

    const auto duplicate = control_plane.dispatch(register_command);
    check(std::holds_alternative<openhdo::DispatchFailure>(duplicate),
          "duplicate registration is rejected");
    if (const auto* failure = std::get_if<openhdo::DispatchFailure>(&duplicate); failure != nullptr) {
        check(failure->error.code == openhdo::DispatchErrorCode::duplicate_device,
              "duplicate registration has typed error");
    }

    const auto invalid_version = openhdo::CommandMessage{
        .version = 2,
        .id = ids.next(),
        .correlation_id = ids.next(),
        .payload = openhdo::SetDeviceStateCommand{.device_id = device.id(),
                                                  .state = openhdo::DeviceState::offline}};
    check(std::holds_alternative<openhdo::DispatchFailure>(control_plane.dispatch(invalid_version)),
          "unsupported command version is rejected");

    check(control_plane.unsubscribe(subscription), "subscription can be removed");
    const auto no_event = openhdo::CommandMessage{
        .version = openhdo::CommandMessage::kVersion,
        .id = ids.next(),
        .correlation_id = ids.next(),
        .payload = openhdo::SetDeviceStateCommand{.device_id = device.id(),
                                                  .state = openhdo::DeviceState::offline}};
    const auto received_before = received.size();
    check(std::holds_alternative<openhdo::DispatchSuccess>(control_plane.dispatch(no_event)),
          "state can be changed after unsubscribe");
    check(received.size() == received_before, "unsubscribed handler receives no event");
    check(log_output.str().find("command.rejected") != std::string::npos,
          "rejections are observable in structured logs");
}

}  // namespace

int main() {
    configuration_tests();
    domain_tests();
    logging_tests();
    control_plane_tests();
    return failures == 0 ? 0 : 1;
}
