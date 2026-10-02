 #include <fcntl.h>
#include <sys/mman.h>
#include <cstring>
#include <fstream>
#include <iostream>
#include <functional>

#include <vector>
#include <thread>
#include "wordindex.h"

// Maximum number of workers processes to use
// [can also configure by running ./revindex_threads --workers N ...]
#define NUM_WORKERS_DEFAULT 8


/*
 * run_workers: Helper for reverse index search: run `num_threads`
 * threads that perform a reverse index search on a subset of the
 * filenames given by `filenames`.  Results should be added to the
 * vector `results`.
 *
 * Arguments:
 *  - term:  The search term
 *  - filenames:  vector of **all filenames in the corpus**
 *  - start_pos: index of the file in filenames that this run of
 *     workers should start.  In other words, if start_pos = 4, the first
 *     filename to process in this function is filenames[4]
 *  - num_threads: numnber of threads to use
 *  - results:  vector of wordindex objects with completed results
 * Returns:  none
 *
 * TODO: Complete this function, using the TODOs below as a guide.  To
 * do this, you might need to add a bit more code than just the TODO
 * blocks, which is fine.
 */
int run_workers(std::string term, std::vector<std::string>& filenames,
                int start_pos, int num_threads, std::vector<wordindex>& results) {

    // TODO:  declare any extra variables (if needed)

    /*
     * TODO:  Start each thread
     * For each thread in num_threads, you should do the following:
     * 1) create a new index object for the file this thread will
     *    process and add it the results vector add it to the results
     *    vector
     * 2) Create the thread to run find_word with the proper arguments
     */
    // TODO:  Implement!




    /*
     * TODO:  join each thread!
     */
    // TODO:  Implement!




    // TODO:  clean up any extra resources (if needed)

    return 0;
}


/*
 * Main function:  check arguments and start processing
 * (You should not need to modify this function, though you can if you want.)
 */
int main(int argc, char* argv[]) {
    char* dirname;
    char* search_term;

    int workers = NUM_WORKERS_DEFAULT;

    if (argc == 3) {
        dirname = argv[1];
        search_term = argv[2];
    } else if (argc == 5) {
        workers = atoi(argv[2]);
        dirname = argv[3];
        search_term = argv[4];
    }
    else {
        fprintf(stderr, "Usage:  %s [--workers N] <dir with text files> <search term>\n", argv[0]);
        exit(1);
    }

    // Load input files from directory
    std::vector<std::string> filenames;
    get_files(filenames, dirname);

    int files_total = filenames.size();

    // Convert search term into a C++ string
    std::string term(search_term);


    std::vector<wordindex> results;
    results.reserve(files_total);  // Pre-allocate space in the vector for all files (DO NOT REMOVE)

    int err = 0;
    int files_completed = 0;  // the number of files that have been processed
    while (files_completed < files_total) {
        int num_threads = 0; // Threads to create in this round

        if ((files_total - files_completed) > workers) {
            num_threads = workers;
        } else {
            num_threads = files_total - files_completed;
        }

        int start_pos = files_completed;

        // Compute the reverse index and search for the term!
        int err = run_workers(term, filenames, start_pos, num_threads, results);
        if (err) {
            break;
        }

        files_completed += num_threads;

    }
    print_occurrences(term, results);

    if (err < 0) {
        printf("ERROR:  %d\n", err);
        exit(1);
    } else {
        exit(0);
    }
}
