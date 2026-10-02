#ifndef __WORDINDEX_H__
#define __WORDINDEX_H__

#include <dirent.h>
#include <stdio.h>
#include <sys/types.h>
#include <unistd.h>
#include <algorithm>
#include <list>
#include <string>
#include <vector>

/*
 * A class to contain the search results for a word in a file
 */
class wordindex {
 public:
  int count = 0;             // the total occurrences of the search term in this file
  std::string filename;      // the name of the file corresponding to this index object
  std::vector<int> indexes;  // the indices of each occurrence of the search term in
			     // this file

  std::vector<std::string> phrases;  // all of the phrases in which the search term was
			             // found in this file
};


/*
 * find_word: reads individual words from a file and compares them
 * with a target search term.
 *
 * When a matching word is found, the location of word and phrase in which
 * the word is contained is added to the index argument.
 *
 * Arguments:
 *  - index: pointer to a wordindex object to store the results
 *  - filename: path to file to search
 *  - target:  search term to find
 * Return value: none
 */
void find_word(wordindex *index, std::string filename, std::string target);

/* print_occurrences: print the results of a given search term on a
 * directory of files
 *
 * The information printed includes the total number of occurrences
 * of the search term followed by each file's name and the locations
 * in the file where the phrase was found
 *
 * Arguments:
 *  - term: the search term used inthe search
 *  - files: vector of wordindex objects containing the search results
 * Return value: None
 */
void print_occurrences(std::string term, std::vector<wordindex>& files);

// *************** HELPER FUNCTIONS BELOW THIS POINT ******************
// (You should not really need to worry about the functions below here)
/*
 * clean_word: helper function to clean up a word read from file makes
 * the word all lower case and removes extraneous punctuation
 *
 * Arguments: a string, word
 * Return value: the cleaned up version of the argument string
 */
std::string clean_word(std::string word);

/*
 * join_string: helper function to join a list of individual words
 * into a single phrase
 *
 * Arguments: a list of strings, words
 * Return value: a single string containing all of the contents of words
 * seperated by spaces
 */
std::string join_string(std::list<std::string> words);


/*
 * get_files: Helper to get all of the filenames of files in a
 * directory
 *
 * Arguments: a reference to a vector of strings to contain the filenames,
 *            filenames
 *            a char* refering to the name of the directory, dirname
 */
void get_files(std::vector<std::string>& filenames, char* dirname);


#endif
