#include <cerrno>
#include <cstring>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

#ifdef _WIN32
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
using SocketHandle = SOCKET;
#else
#include <netdb.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>
using SocketHandle = int;
static constexpr SocketHandle INVALID_SOCKET = -1;
static constexpr int SOCKET_ERROR = -1;
#endif

namespace {

struct Url {
    std::string host;
    std::string port;
    std::string path;
};

std::string jsonEscape(const std::string& input) {
    std::ostringstream out;
    for (unsigned char ch : input) {
        switch (ch) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (ch < 0x20) {
                    const char* hex = "0123456789abcdef";
                    out << "\\u00" << hex[(ch >> 4) & 0xf] << hex[ch & 0xf];
                } else {
                    out << static_cast<char>(ch);
                }
        }
    }
    return out.str();
}

Url parseUrl(const std::string& input) {
    const std::string scheme = "http://";
    if (input.compare(0, scheme.size(), scheme) != 0) {
        throw std::runtime_error("only http:// URLs are supported");
    }

    std::string rest = input.substr(scheme.size());
    std::string hostPort = rest;
    std::string path;
    std::string::size_type slash = rest.find('/');
    if (slash != std::string::npos) {
        hostPort = rest.substr(0, slash);
        path = rest.substr(slash);
    }

    if (hostPort.empty()) {
        throw std::runtime_error("URL host is empty");
    }

    Url url;
    std::string::size_type colon = hostPort.rfind(':');
    if (colon != std::string::npos) {
        url.host = hostPort.substr(0, colon);
        url.port = hostPort.substr(colon + 1);
    } else {
        url.host = hostPort;
        url.port = "80";
    }
    url.path = path.empty() ? "" : path;
    return url;
}

std::string endpointPath(const Url& base) {
    if (base.path.empty() || base.path == "/") {
        return "/api/v1/exec";
    }
    if (base.path.back() == '/') {
        return base.path + "api/v1/exec";
    }
    return base.path + "/api/v1/exec";
}

std::string readStdin() {
    std::ostringstream out;
    out << std::cin.rdbuf();
    return out.str();
}

void closeSocket(SocketHandle socket) {
#ifdef _WIN32
    closesocket(socket);
#else
    close(socket);
#endif
}

SocketHandle connectTcp(const std::string& host, const std::string& port) {
    addrinfo hints{};
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_family = AF_UNSPEC;

    addrinfo* result = nullptr;
    int rc = getaddrinfo(host.c_str(), port.c_str(), &hints, &result);
    if (rc != 0) {
        throw std::runtime_error(std::string("getaddrinfo failed: ") + gai_strerror(rc));
    }

    SocketHandle socket = INVALID_SOCKET;
    for (addrinfo* item = result; item != nullptr; item = item->ai_next) {
        socket = ::socket(item->ai_family, item->ai_socktype, item->ai_protocol);
        if (socket == INVALID_SOCKET) {
            continue;
        }
        if (::connect(socket, item->ai_addr, static_cast<int>(item->ai_addrlen)) == 0) {
            break;
        }
        closeSocket(socket);
        socket = INVALID_SOCKET;
    }

    freeaddrinfo(result);
    if (socket == INVALID_SOCKET) {
        throw std::runtime_error("could not connect to rrepl server");
    }
    return socket;
}

void sendAll(SocketHandle socket, const std::string& data) {
    std::size_t sent = 0;
    while (sent < data.size()) {
        int n = send(socket, data.data() + sent, static_cast<int>(data.size() - sent), 0);
        if (n == SOCKET_ERROR) {
            throw std::runtime_error("send failed");
        }
        sent += static_cast<std::size_t>(n);
    }
}

std::string receiveAll(SocketHandle socket) {
    std::string response;
    char buffer[4096];
    while (true) {
        int n = recv(socket, buffer, sizeof(buffer), 0);
        if (n <= 0) {
            break;
        }
        response.append(buffer, buffer + n);
    }
    return response;
}

std::string responseBody(const std::string& response) {
    std::string marker = "\r\n\r\n";
    std::string::size_type pos = response.find(marker);
    if (pos == std::string::npos) {
        return response;
    }
    return response.substr(pos + marker.size());
}

} // namespace

int main(int argc, char** argv) {
    try {
#ifdef _WIN32
        WSADATA wsa{};
        if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
            throw std::runtime_error("WSAStartup failed");
        }
#endif

        std::string baseUrl = argc > 1 ? argv[1] : "http://127.0.0.1:8765";
        std::string session = argc > 2 ? argv[2] : "default";
        std::string code;
        if (argc > 3) {
            for (int i = 3; i < argc; ++i) {
                if (!code.empty()) {
                    code += ' ';
                }
                code += argv[i];
            }
        } else {
            code = readStdin();
        }
        if (code.empty()) {
            code = "print('hello from C++ rrepl client')";
        }

        Url url = parseUrl(baseUrl);
        std::string body = "{\"code\":\"" + jsonEscape(code) + "\",\"session\":\"" + jsonEscape(session) + "\"}";
        std::ostringstream request;
        request << "POST " << endpointPath(url) << " HTTP/1.1\r\n"
                << "Host: " << url.host << ":" << url.port << "\r\n"
                << "Content-Type: application/json\r\n"
                << "Content-Length: " << body.size() << "\r\n"
                << "Connection: close\r\n\r\n"
                << body;

        SocketHandle socket = connectTcp(url.host, url.port);
        sendAll(socket, request.str());
        std::string response = receiveAll(socket);
        closeSocket(socket);

        std::cout << responseBody(response) << std::endl;

#ifdef _WIN32
        WSACleanup();
#endif
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "rrepl_client: " << exc.what() << std::endl;
#ifdef _WIN32
        WSACleanup();
#endif
        return 1;
    }
}
