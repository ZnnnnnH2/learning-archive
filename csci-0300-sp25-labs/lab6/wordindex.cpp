#include <dirent.h>
#include <stdio.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <algorithm>
#include <list>
#include <string>
#include <vector>


#include "wordindex.h"

/*
 * clean_word:  See description in wordinex.h
 */
std::string clean_word(std::string word) {
    transform(word.begin(), word.end(), word.begin(), ::tolower);
    int trailing = 0;
    for (int i = word.length() - 1; i >= 0; i--) {
	if (word[i] != 39 && ispunct(word[i])) {  // 39 = '
	    trailing++;
	} else {
	    break;
	}
    }
    if (trailing > 0) {
	word.erase(word.length() - trailing, trailing);
    }

    return word;
}

/*
 * join_string:  See description in wordindex.h
 */
std::string join_string(std::list<std::string> words) {
    std::string phrase = "";
    for (auto& str : words) {
	phrase += str + " ";
    }
    phrase.pop_back();  // removes last space
    return phrase;
}

/*
 * find_word:  See description in wordinex.h
 */
void find_word(wordindex* index, std::string filename, std::string target) {
    index->filename = filename;
    FILE* file = fopen(index->filename.c_str(), "r");
    if (!file) {
	return;
    } else {
	int loc = 1;
	std::list<int> indices;
	std::list<std::string> context;

	while (1) {
	    char buf[255];
	    if (fscanf(file, "%s", buf) != EOF) {
		std::string word(buf);
		std::string edited_word = clean_word(word);
		// keep track of matching indices
		if (target.compare(edited_word) == 0) {
		    indices.push_back(loc);
		}

		// keep a running list of the last 5 words as context
		if (loc > 5) {
		    context.pop_front();
		}
		context.push_back(word);

		// once the current location is two words past a
		// matching index add the matching index and phrase to target.
		if (indices.size() > 0 && loc == (indices.front() + 2)) {
		    std::string phrase = join_string(context);
		    index->phrases.push_back(phrase);
		    index->indexes.push_back(indices.front());
		    indices.pop_front();
		}

		// increment the location
		loc++;
	    } else {
		break;
	    }
	}
	while (indices.size() > 0) {
	    std::string phrase = join_string(context);
	    index->phrases.push_back(phrase);
	    index->indexes.push_back(indices.front());
	    indices.pop_front();
	}
	fclose(file);
	index->count = index->indexes.size();

	return;
    }
}

/*
 * print_occurrences:  See description in wordinex.h
 */
void print_occurrences(std::string term, std::vector<wordindex>& files) {
    int total_occurrences = 0;
    for (auto &f : files) {
        total_occurrences += f.indexes.size();
    }
    printf("Found %d instances of %s.\n", total_occurrences, term.c_str());

    for (auto& f : files) {
	if (f.indexes.size()) {
	    printf("%s found in %s at locations:\n", term.c_str(),
		   f.filename.c_str());
	    int num = 0;
	    for (auto itr = f.indexes.begin(); itr != f.indexes.end(); itr++) {
		printf("Index %d: %s\n", *itr, f.phrases[num].c_str());
		num++;
	    }
	    printf("\n");
	} else {
	    printf("%s not found in %s\n", term.c_str(), f.filename.c_str());
	}
	f.indexes.clear();
	f.phrases.clear();
    }
}

/* A function to get all of the filenames of files in a directory
 *
 * Arguments: a reference to a vector of strings to contain the filenames,
 *            filenames
 *            a char* refering to the name of the directory, dirname
 */
void get_files(std::vector<std::string>& filenames, char* dirname) {
    DIR* dir = opendir(dirname);
    if (dir == NULL) {
	perror("Could not open source directory");
	exit(1);
    }

    std::string dirname_base = std::string(dirname) + "/";
    struct dirent* ent;
    while ((ent = readdir(dir)) != NULL) {
	if (ent->d_name[0] != '.') {
	    std::string name(ent->d_name);
	    filenames.push_back(dirname_base + name);
	}
    }
    closedir(dir);
}
