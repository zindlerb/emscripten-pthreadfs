# Emscripten
EMCC = emcc
FILE_PACKAGER = ../file_packager.py

# Define some folders
EMTESTS = emscripten-tests
NODEJSTESTS = nodejs-tests
PACKAGERTESTS = packager-tests
OBJ = out/bc

PTHREADFS_JS = ../library_pthreadfs.js
PTHREADFS_H = ../pthreadfs.h
PTHREADFS_CPP = ../pthreadfs.cpp

PACKAGER_INPUT_SMALL = $(PACKAGERTESTS)/input/small/smallfile.txt
PACKAGER_INPUT_MEDIUMLARGE = $(PACKAGERTESTS)/input/mediumlarge/subfolder/mediumfile.txt $(PACKAGERTESTS)/input/mediumlarge/bigfile.txt
PACKAGER_INPUT = $(PACKAGER_INPUT_SMALL) $(PACKAGER_INPUT_MEDIUMLARGE)

SQLITE_SRC = ../../tests/third_party/sqlite
SQLITE_BENCHMARK_SRC = ../../tests/sqlite


.PHONY: all 
all: sqlite emscripten-tests packager-tests jsops-tests


# Optimization Flags
## With debugging flags enabled, optimization level is O0.
OPTIMIZATION_LEVEL = O2
DEBUGGING_FLAGS = -gsource-map \
	--source-map-base http://localhost:8992/$(EMTESTS)/

CFLAGS = \
	-$(OPTIMIZATION_LEVEL) \
	-Wall \
	-pthread \
	-I..

# Allocate 128 MiB to prevent OOM errors in some tests.
LINK_FLAGS =  \
	-pthread \
	-s PROXY_TO_PTHREAD \
	-$(OPTIMIZATION_LEVEL) \
	-s INITIAL_MEMORY=134217728 \
	$(DEBUGGING_FLAGS)

.PHONY: clean
clean:
	rm -rf dist/*
	rm -rf out/

# Don't delete my precious object files
.PRECIOUS: $(OBJ)/%.out

$(OBJ)/pthreadfs.o : $(PTHREADFS_CPP) $(PTHREADFS_H)
	mkdir -p $(OBJ)
	$(EMCC) -c $(CFLAGS) $< -o $@

.PHONY: sqlite
sqlite: $(addprefix dist/sqlite/, $(addsuffix .html, $(notdir $(basename $(wildcard $(SQLITE_BENCHMARK_SRC)/*.c)))))
	@echo 'Building SQLite Tests' $?

$(OBJ)/sqlite3.o: $(SQLITE_SRC)/sqlite3.c
	mkdir -p $(OBJ)
	$(EMCC) $(CFLAGS) -c $< -o $@

$(OBJ)/sqlite/%.o : $(SQLITE_BENCHMARK_SRC)/%.c
	mkdir -p $(OBJ)/sqlite/
	$(EMCC) -c $(CFLAGS) -I$(SQLITE_SRC) $< -o $@

dist/sqlite/%.html : $(OBJ)/sqlite/%.o $(OBJ)/pthreadfs.o $(OBJ)/sqlite3.o sqlite/sqlite-prejs.js $(PTHREADFS_JS) 
	mkdir -p dist/sqlite/
	$(EMCC) $(LINK_FLAGS) --js-library=$(PTHREADFS_JS) --pre-js=$(word 4,$^) $< $(word 2,$^) $(word 3,$^) -o $@

$(OBJ)/%.o : $(EMTESTS)/%.cpp
	mkdir -p $(OBJ)
	$(EMCC) -c $(CFLAGS) $< -o $@

$(OBJ)/%.o : $(PACKAGERTESTS)/%.cpp
	mkdir -p $(OBJ)
	$(EMCC) -c $(CFLAGS) $< -o $@

.PHONY: emscripten-tests
emscripten-tests: $(addprefix dist/, $(addsuffix .html, $(basename $(wildcard $(EMTESTS)/*.cpp))))
	@echo 'Building tests for Chrome' $?

dist/$(EMTESTS)/%.html : $(OBJ)/%.o $(OBJ)/pthreadfs.o $(PTHREADFS_JS)
	mkdir -p dist/$(EMTESTS)
	$(EMCC) $(LINK_FLAGS) --js-library=$(PTHREADFS_JS) $< $(word 2,$^) -o $@

.PHONY: emscripten-tests-nodejs
emscripten-tests-nodejs: $(addprefix dist/$(NODEJSTESTS)/, $(notdir $(addsuffix .js, $(basename $(wildcard $(EMTESTS)/*.cpp)))))
	@echo 'Building tests for Node.js' $?

dist/$(NODEJSTESTS)/%.js : $(OBJ)/%.o $(OBJ)/pthreadfs.o $(PTHREADFS_JS)
	mkdir -p dist/$(NODEJSTESTS)
	$(EMCC) $(LINK_FLAGS) --js-library=$(PTHREADFS_JS) $< $(word 2,$^) -o $@
	

# Compiling the packager tests requires manual creation of the following files
# - $(PACKAGERTESTS)/input/small/smallfile.txt: Size 188 bytes, first line "These are the contents of a very small file."
# - $(PACKAGERTESTS)/input/mediumlarge/subfolder/mediumfile.txt: Size 138670 bytes, first line "Begin mediumfile.txt -------------------------------------------"
# - $(PACKAGERTESTS)/input/mediumlarge/bigfile.txt: Size 212992000 bytes, first line "Begin bigfile.txt ----------------------------------------------"
.PHONY: packager-tests
packager-tests: dist/$(PACKAGERTESTS)/preloading_without_pthreadfs.html dist/$(PACKAGERTESTS)/preloading.html dist/$(PACKAGERTESTS)/load_package_sync.html dist/$(PACKAGERTESTS)/load_package_async.html

# Create the file packages
dist/$(PACKAGERTESTS)/pkg_preload_small.js: $(PACKAGER_INPUT_SMALL) $(FILE_PACKAGER)
	mkdir -p dist/$(PACKAGERTESTS)/
	python3 $(FILE_PACKAGER) $(addsuffix .data, $(basename $@)) --preload ./$(PACKAGERTESTS)/input/small@/persistent --use_pthreadfs --js-output=$@
dist/$(PACKAGERTESTS)/pkg_preload_mediumlarge.js: $(PACKAGER_INPUT_MEDIUMLARGE) $(FILE_PACKAGER)
	mkdir -p dist/$(PACKAGERTESTS)/
	python3 $(FILE_PACKAGER) $(addsuffix .data, $(basename $@)) --preload ./$(PACKAGERTESTS)/input/mediumlarge@/persistent --use_pthreadfs --js-output=$@

dist/$(PACKAGERTESTS)/pkg_intermediate_small.js: $(PACKAGER_INPUT_SMALL) $(FILE_PACKAGER)
	mkdir -p dist/$(PACKAGERTESTS)/
	python3 $(FILE_PACKAGER) $(addsuffix .data, $(basename $@)) --preload ./$(PACKAGERTESTS)/input/small@/persistent/intermediate_loading --use_pthreadfs --js-output=$@
dist/$(PACKAGERTESTS)/pkg_intermediate_mediumlarge.js: $(PACKAGER_INPUT_MEDIUMLARGE) $(FILE_PACKAGER)
	mkdir -p dist/$(PACKAGERTESTS)/
	python3 $(FILE_PACKAGER) $(addsuffix .data, $(basename $@)) --preload ./$(PACKAGERTESTS)/input/mediumlarge@/persistent/intermediate_loading --use_pthreadfs --js-output=$@

	
dist/$(PACKAGERTESTS)/preloading_without_pthreadfs.html: $(OBJ)/preloading.o $(PACKAGER_INPUT)
	mkdir -p dist/$(PACKAGERTESTS)
	$(EMCC) $(LINK_FLAGS) -o $@ --preload-file $(PACKAGERTESTS)/input/small@/persistent --preload-file $(PACKAGERTESTS)/input/mediumlarge@/persistent $<

dist/$(PACKAGERTESTS)/preloading.html: $(OBJ)/preloading.o $(OBJ)/pthreadfs.o dist/$(PACKAGERTESTS)/pkg_preload_small.js dist/$(PACKAGERTESTS)/pkg_preload_mediumlarge.js $(PTHREADFS_JS)
	mkdir -p dist/$(PACKAGERTESTS)
	$(EMCC) $(LINK_FLAGS) -o $@ --js-library=$(PTHREADFS_JS)  --pre-js $(word 3,$^) --pre-js $(word 4,$^)  $< $(word 2,$^) 

dist/$(PACKAGERTESTS)/load_package_sync.html: $(OBJ)/load_package_sync.o $(OBJ)/pthreadfs.o dist/$(PACKAGERTESTS)/pkg_intermediate_small.js dist/$(PACKAGERTESTS)/pkg_intermediate_mediumlarge.js $(PTHREADFS_JS)
	mkdir -p dist/$(PACKAGERTESTS)
	$(EMCC) $(LINK_FLAGS) -o $@ --js-library=$(PTHREADFS_JS) $< $(word 2,$^)

dist/$(PACKAGERTESTS)/load_package_async.html: $(OBJ)/load_package_async.o $(OBJ)/pthreadfs.o dist/$(PACKAGERTESTS)/pkg_intermediate_small.js $(PTHREADFS_JS)
	mkdir -p dist/$(PACKAGERTESTS)
	$(EMCC) $(LINK_FLAGS) -o $@ --js-library=$(PTHREADFS_JS) $< $(word 2,$^)

JSOPSTESTS = jsops-tests
.PHONY: jsops-tests
jsops-tests: dist/$(JSOPSTESTS)/write_from_main_thread.html dist/$(JSOPSTESTS)/read_from_main_thread.html

$(OBJ)/%.o : $(JSOPSTESTS)/%.cpp
	mkdir -p $(OBJ)
	$(EMCC) -c $(CFLAGS) $< -o $@

dist/$(JSOPSTESTS)/write_from_main_thread.html: $(OBJ)/write_from_main_thread.o $(OBJ)/pthreadfs.o $(JSOPSTESTS)/write_from_main_thread_pre.js $(PTHREADFS_JS)
	mkdir -p dist/$(JSOPSTESTS)
	$(EMCC) $(LINK_FLAGS) -o $@ --js-library=$(PTHREADFS_JS) --pre-js $(word 3,$^) $< $(word 2,$^)

dist/$(JSOPSTESTS)/read_from_main_thread.html: $(OBJ)/read_from_main_thread.o $(OBJ)/pthreadfs.o $(PTHREADFS_JS)
	mkdir -p dist/$(JSOPSTESTS)
	$(EMCC) $(LINK_FLAGS) -o $@ --js-library=$(PTHREADFS_JS) $< $(word 2,$^)  
