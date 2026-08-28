#include <iostream>
#include <regex>
#include <string>

int main() {
    std::string request;
    std::getline(std::cin, request);

    std::smatch match;
    const std::regex case_id_pattern("\\\"case_id\\\":\\\"([^\\\"]+)\\\"");
    const std::regex ply_pattern("\\\"ply\\\":([0-9]+)");
    const std::regex board_size_pattern("\\\"board_size\\\":([0-9]+)");
    if (!std::regex_search(request, match, case_id_pattern)) {
        return 2;
    }
    const std::string case_id = match[1];
    if (!std::regex_search(request, match, ply_pattern)) {
        return 3;
    }
    const int ply = std::stoi(match[1]);
    if (!std::regex_search(request, match, board_size_pattern)) {
        return 4;
    }
    const int board_size = std::stoi(match[1]);

    const int row = ply == 0 ? board_size / 2 : board_size;
    const int col = ply == 0 ? board_size / 2 : board_size;
    std::cout << "debug: received ply=" << ply << '\n';
    std::cout << "{\"case_id\":\"" << case_id << "\",\"move\":[" << row << ',' << col
              << "]}" << std::endl;
    std::cout << "debug: response emitted" << std::endl;
}
