#include <openhdo/configuration.hpp>
#include <openhdo/runtime.hpp>

#include <iostream>
#include <variant>

int main(const int argc, char* argv[]) {
    const auto configuration = openhdo::load_configuration(openhdo::configuration_from_environment());
    if (const auto* error = std::get_if<openhdo::ConfigurationError>(&configuration);
        error != nullptr) {
        std::cerr << "configuration error [" << error->key << "]: " << error->message << '\n';
        return 2;
    }

    const auto& config = std::get<openhdo::Configuration>(configuration);
    openhdo::Logger logger(std::clog, config.log_level);
    logger.info("server", "foundation.ready", {{"instance", config.instance_name},
                                                 {"config_version", "1"},
                                                 {"command_path", "in-memory"}});
    return openhdo::run_command_line("openhdo-server", argc, argv);
}
