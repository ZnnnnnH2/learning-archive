CXX = g++
CXXFLAGS = -g -Wall -Wextra -Wpedantic -fsanitize=address -Wno-unused-parameter -Wno-unused-variable

EXECS = revindex_sequential revindex_parallel

all: $(EXECS)

books:
	wget https://csci0300.github.io/assign/labs/assets/lab5-books.tar.gz
	tar -xzf lab5-books.tar.gz
	rm lab5-books.tar.gz
	mkdir -p tiny
	cp -pv books/Ion* books/The\ Works* tiny/
	wget https://csci0300.github.io/assign/labs/assets/lab5-expected-output.tar.gz
	tar -xvf lab5-expected-output.tar.gz
	rm lab5-expected-output.tar.gz

format:
	clang-format -style=Google -i revindex_procs.cpp

revindex_sequential: books revindex_sequential.cpp wordindex.h wordindex.o
	$(CXX) $(CXXFLAGS) -o $@ $(filter-out $<,$^)

revindex_parallel: books revindex_procs.cpp wordindex.h wordindex.o
	$(CXX) $(CXXFLAGS) -o $@ $(filter-out $<,$^)

wordindex.o: wordindex.cpp
	$(CXX) $(CXXFLAGS) -c $<

clean:
	rm -fv $(EXECS) wordindex.o

.PHONY: all check clean
