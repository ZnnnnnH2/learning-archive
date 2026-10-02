CXX = g++
CXXFLAGS = -g -Wall -Wextra -Wpedantic -fsanitize=address -Wno-unused-parameter -Wno-unused-variable

EXECS = revindex_sequential revindex_threads

OUT_DIR = expected_output

all: $(EXECS)

books:
	wget https://csci0300.github.io/assign/labs/assets/lab5-books.tar.gz
	tar -xzf lab5-books.tar.gz
	rm lab5-books.tar.gz
	mkdir -p tiny
	cp -pv books/Ion* books/The\ Works* tiny/

format:
	clang-format -style=Google -i revindex_procs.cpp

revindex_sequential: books revindex_sequential.cpp wordindex.h wordindex.o
	$(CXX) $(CXXFLAGS) -o $@ $(filter-out $<,$^)
	$(MAKE) expected

revindex_threads: books revindex_threads.cpp wordindex.h wordindex.o
	$(CXX) $(CXXFLAGS) -o $@ $(filter-out $<,$^)

wordindex.o: wordindex.cpp
	$(CXX) $(CXXFLAGS) -c $<

expected: revindex_sequential | $(OUT_DIR)

$(OUT_DIR):
	$(info ***************)
	$(info Generating expected output files.  This may take a few minutes, but only needs to be done once.)
	$(info ***************)
	mkdir -p $(OUT_DIR)/books
	mkdir -p $(OUT_DIR)/tiny
	./revindex_sequential books hello > $(OUT_DIR)/books/hello.txt
	./revindex_sequential books book > $(OUT_DIR)/books/book.txt
	./revindex_sequential books peace > $(OUT_DIR)/books/peace.txt
	./revindex_sequential books the > $(OUT_DIR)/books/the.txt
	./revindex_sequential books world > $(OUT_DIR)/books/world.txt

	./revindex_sequential tiny hello > $(OUT_DIR)/tiny/hello.txt
	./revindex_sequential tiny book > $(OUT_DIR)/tiny/book.txt
	./revindex_sequential tiny peace > $(OUT_DIR)/tiny/peace.txt
	./revindex_sequential tiny the > $(OUT_DIR)/tiny/the.txt
	./revindex_sequential tiny world > $(OUT_DIR)/tiny/world.txt


clean:
	rm -fv $(EXECS) wordindex.o

.PHONY: all check clean
