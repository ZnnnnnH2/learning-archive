
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/mman.h>
#include <sys/wait.h>

#include <cstring>

#include "wordindex.h"

// Maximum number of workers processes to use
// [can also configure by running ./revindex_parallel --workers N ...]
#define NUM_WORKERS_DEFAULT 8

// Prototypes for functions in this file
// [See definitions below for documentation]
int process_input(std::string term, std::vector<std::string>& filenames,
                  int workers);
void process_file(std::string term, std::string filename, int pipefd);
void read_process_results(wordindex *ind, int pipefd);
char* serialize_word_index(wordindex* f, size_t* size_p);
void deserialize_word_index(char* buffer, size_t size, wordindex* ind);


/*
 * process_input: Perform a reverse index search for `term` in the
 * files given by `filenames` using multiple worker processes
 *
 * Arguments:
 *  - term:  the search term
 *  - filenames: vector of names of files to search
 *  - workers:  number of worker processes to use
 * Returns: none
 *
 * TODO: Complete this function, use the TODOs below as a guide.  To
 * do this, you might need to add a bit more code than just the TODO
 * blocks, which is fine.
 */
int process_input(std::string term, std::vector<std::string>& filenames,
                  int workers) {

    int files_total = filenames.size();
    int files_completed = 0;  // the number of files that have been processed

    std::vector<wordindex> results;

    int* pids = (int*)malloc(workers * sizeof(int));
    // TODO:  declare any extra variables (if needed)

    /*
     * While the number of files that have been processed is less than the number
     * of files that need to be processed, do the steps described below:
     */
    while (files_completed < files_total) {
	// number of processes to be created in this iteration of the loop
	int num_procs = 0;
	if ((files_total - files_completed) > workers) {
	    num_procs = workers;
	} else {
	    num_procs = files_total - files_completed;
	}

	/*
	 * TODO:  Start worker processes
	 * For each process you should do the following:
	 *   1) create a pipe for this process
	 *   2) fork a child process: the child only needs to call
	 *      process_file (which will write to pipe)
	 *   3) in the parent process, add the child's pid to the array of pids
	 */
	// TODO:  Implement!

	/*
	 * TODO:  Collect results from this round of child processes
	 * For each processes you should do the following:
	 *   1) Create a wordindex object for the process (set the
	 *      filename from the filenames array)
	 *   2) Call read_process_results and pass it the correct pipe to read from
	 *       - HINT:  How will you know which pipe to read from?
	 *         Need to store this info somewhere when you create the pipe!
	 *   3) Add the wordindex object for this file to the `results` vector
	 */
	// TODO:  Implement!

	/*
	 * TODO:  Wait for each process this round
	 * For each process you should do the following:
	 * 1) Call waitpid to make sure the process has completed
	 */
	// TODO:  Implement!

	files_completed += num_procs;
    }

    print_occurrences(term, results);

    free(pids);
    // TODO:  clean up any extra resources (if needed)

    return 0;
}



/*
 * process_file: Perform a reverse index search on a single file.
 * This function is meant to be run by each worker process.
 *
 * TODO:  in this function, you should:
 *   1) Create a wordindex object and compute the reverse index for this
 *      file using find_word
 *   2) Use the serialize_word_index function to convert the wordindex
 *      object into bytes you can send over the pipe
 *   3) Send the data to the parent by writing to the pipe
 *      - HINT: How will the parent know how much data to read?
 *         Consider what else you may need to send first.
 *   4) Close the pipe
 *
 * Arguments:
 *  - term:  the search term
 *  - filename:  path to the file to search
 *  - pipefd:  FD of the pipe to write results to
 * Return value: none
 */
void process_file(std::string term, std::string filename, int pipefd) {
    // TODO:  Implement!  (See steps in comment above)
}

/*
 * read_process_results: Read the search results sent by the worker
 * process via a pipe.  This function is meant to be called by the
 * parent process, once per worker.
 *
 * In this function, you should:
 * 1) read the data the child process sent through
 *    the pipe
 *      - Hint: how to know how much data to read?  Perhaps you can
 *      send some information at the start of the message to help.
 * 2) Use the deserialize_word_index function to convert the data back
      into a wordindex object
 * 3) close the pipe
 *
 * Arguments:
 *  - ind:  a pointer to the wordindex object to fill in
 *  - pipefd:  FD of the pipe to read from
 * Return value: none
 */
void read_process_results(wordindex* ind, int pipefd) {
    // TODO:  Implement (See steps in comment above)
}


/*
 * serialize_word_index: helper function to convert a wordindex object
 * into a an array of bytes so it can be written to a pipe.
 * Arguments:
 *   - f:  pointer to a wordindex object
 *   - size_p: Pointer to a variable of type size_t.  When function
 *     returns, the size of the array of bytes will be written here.
 *
 * Returns:  pointer to array of bytes containing data from f
 *  - NOTE: The array returned is allocated using malloc; the caller is
 *  responsible for freeing this data!
 *
 * (You should not need to modify this function, though you can if you want.)
 */
char* serialize_word_index(wordindex* f, size_t *size_p) {
    /*
     * Extra details: this function writes the data in order with the
     * index and the phrase seperated by a colon: length of a string
     * containing the index, the index, length of the phrase, the
     * phrase.  The resulting string is null-terminated.
     */
    std::string val = "";
    for (unsigned int i = 0; i < f->indexes.size(); i++) {
        std::string ind = std::to_string(f->indexes[i]);
        std::string ind_result = std::to_string(ind.length()) + ":" + ind;
        std::string phrase_result =
            std::to_string(f->phrases[i].length()) + ":" + f->phrases[i];
        val += ind_result + phrase_result;
    }

    size_t total_length = val.size() + 1;
    char* string_bytes = (char*)malloc(total_length);
    memset(string_bytes, 0, total_length);
    memcpy(string_bytes, val.c_str(), total_length);

    *size_p = total_length;
    return string_bytes;
}

/*
 * deserialize_word_index: helper function to convert an array of
 * bytes read from pipe back into a wordindex object
 * Arguments:
 *   - buffer: Pointer to array of bytes containing the data
 *   - ind:  pointer to the wordindex object to set up
 * Returns:  none
 *
 * (You should not need to modify this function, though you can if you want.)
 */
void deserialize_word_index(char* buffer, size_t size, wordindex* ind) {
    char* tok = NULL;


    for (int i = 0; buffer[i] != '\0';) {
        tok = strtok(buffer + i, ":");  // point to length of index
	i += strlen(tok) + 1;           // i should point at index
	int len_index = atoi(tok);

	//printf("buffer %p, i %d, index %d\n", buffer, i, len_index);
        std::string phrase_ind =
	    std::string(buffer + i, len_index);  // copy from i to len_index
        int newind = stoi(phrase_ind);
	ind->indexes.push_back(newind);
	i += len_index;
	tok = strtok(buffer + i, ":");
	len_index = atoi(tok);  // point to length of phrase
	i += strlen(tok) + 1;   // i should point at phrasee

        std::string phrase = std::string(buffer + i, len_index);
	ind->phrases.push_back(phrase);
	i += len_index;
    }
}

/*
 * Main function:  check arguments and start processing
 * (You should not need to modift this function, though you can if you want.)
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

    int num_files = filenames.size();

    // Convert search term into a C++ string
    std::string term(search_term);

    // Compute the reverse index and search for the term!
    int err = process_input(term, filenames, workers);

    if (err < 0) {
	printf("ERROR:  %d\n", err);
	exit(1);
    } else {
	exit(0);
    }
}
