#include <fcntl.h>
#include <sys/mman.h>
#include <cstring>
#include <fstream>
#include <iostream>
#include "wordindex.h"

int process_input(std::string term, std::vector<std::string>& filenames) {
    int total_files = filenames.size();
    std::vector<wordindex> results;

    for (int i = 0; i < total_files; i++) {
        wordindex index;
        find_word(&index, filenames[i], term);
        results.push_back(index);
    }
    print_occurrences(term, results);
    return 0;
}

int main(int argc, char* argv[]) {
    char* dirname;
    char* search_term;

    if (argc == 3) {
        dirname = argv[1];
	search_term = argv[2];
    } else {
	fprintf(stderr, "Usage:  %s <dir with text files> <search term>\n", argv[0]);
	exit(1);
    }

    // Load input files from directory
    std::vector<std::string> filenames;
    get_files(filenames, dirname);

    int num_files = filenames.size();

    // Convert search term into a C++ string
    std::string term(search_term);

    // Compute the reverse index and search for the term!
    int err = process_input(term, filenames);

    if (err < 0) {
	printf("ERROR:  %d\n", err);
	exit(1);
    } else {
	exit(0);
    }
}
