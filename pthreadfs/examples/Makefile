# Emscripten
EMCC = emcc
FILE_PACKAGER = ../../tools/file_packager.py

# Define some folders
EMTESTS = emscripten-tests
SQLITETESTS = sqlite-speedtest
PRELOADTESTS = preload-tests
OBJ = out/bc

PTHREADFS_JS = ../library_pthreadfs.js
PTHREADFS_H = ../pthreadfs.h
PTHREADFS_CPP = ../pthreadfs.cpp

PRELOADFILES = $(PRELOADTESTS)/input/smallfile.txt $(PRELOADTESTS)/input/subfolder/mediumfile.txt $(PRELOADTESTS)/input/bigfile.txt

# I got this handy makefile syntax from : https://github.com/mandel59/sqlite-wasm (MIT License) Credited in LICENSE
# To use another version of Sqlite, visit https://www.sqlite.org/download.html and copy the appropriate values here:
SQLITE_AMALGAMATION = sqlite-amalgamation-3350000
SQLITE_AMALGAMATION_ZIP_URL = https://www.sqlite.org/2021/sqlite-amalgamation-3350000.zip
SQLITE_AMALGAMATION_ZIP_SHA1 = ba64bad885c9f51df765a9624700747e7bf21b79
SQLITE_H = sqlite3.h
SQLITE_SPEEDTEST = speedtest1.c
SQLITE_SPEEDTEST_URL = https://sqlite.org/src/raw/5e5b805f24cc939656058f6a498f5a2160f9142e4815c54faf758ec798d4cdad?at=speedtest1.c
SQLITE_SPEEDTEST_SHA1 = f0edde2ad68f090e4676ac30042e0f6b765a8528

.PHONY: all 
all: sqlite-speedtest emscripten-tests

## cache
cache/$(SQLITE_AMALGAMATION).zip:
	mkdir -p cache
	curl -LsSf '$(SQLITE_AMALGAMATION_ZIP_URL)' -o $@

cache/$(SQLITE_SPEEDTEST):
	mkdir -p cache
	curl -LsSf '$(SQLITE_SPEEDTEST_URL)' -o $@


## sqlite-src
.PHONY: sqlite-src
sqlite-src: sqlite-src/$(SQLITE_AMALGAMATION) sqlite-src/$(SQLITE_SPEEDTEST)

sqlite-src/$(SQLITE_AMALGAMATION): cache/$(SQLITE_AMALGAMATION).zip sqlite-src/$(SQLITE_AMALGAMATION)/$(EXTENSION_FUNCTIONS)
	mkdir -p sqlite-src/$(SQLITE_AMALGAMATION)
	echo '$(SQLITE_AMALGAMATION_ZIP_SHA1)  ./cache/$(SQLITE_AMALGAMATION).zip' > cache/check.txt
	shasum -c cache/check.txt
	# We don't delete the sqlite_amalgamation folder. That's a job for clean
	# Also, the extension functions get copied here, and if we get the order of these steps wrong,
	# this step could remove the extension functions, and that's not what we want
	unzip -u 'cache/$(SQLITE_AMALGAMATION).zip' -d sqlite-src/
	touch $@

sqlite-src/$(SQLITE_AMALGAMATION)/$(SQLITE_H): sqlite-src/$(SQLITE_AMALGAMATION)

sqlite-src/$(SQLITE_SPEEDTEST): cache/$(SQLITE_SPEEDTEST)
	mkdir -p sqlite-src/$(SQLITE_AMALGAMATION)
	echo '$(SQLITE_SPEEDTEST_SHA1)  ./cache/$(SQLITE_SPEEDTEST)' > cache/check.txt
	shasum -c cache/check.txt
	cp 'cache/$(SQLITE_SPEEDTEST)' $@

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

CFLAGS_SQLITE = \
	$(CFLAGS) \
	-DSQLITE_ENABLE_MEMSYS5 \
	-D_HAVE_SQLITE_CONFIG_H \
	-DSQLITE_OMIT_LOAD_EXTENSION \
	-DSQLITE_DISABLE_LFS \
	-DSQLITE_THREADSAFE=0 \
	-DSQLITE_ENABLE_NORMALIZE \
	-Isqlite-src/$(SQLITE_AMALGAMATION)/

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
	rm -f cache/*
	rm -rf sqlite-src/

$(OBJ)/sqlite3.o: sqlite-src/$(SQLITE_AMALGAMATION)
	mkdir -p $(OBJ)
	$(EMCC) $(CFLAGS) -c sqlite-src/$(SQLITE_AMALGAMATION)/sqlite3.c -o $@

$(OBJ)/speedtest1.o: sqlite-src/$(SQLITE_SPEEDTEST) sqlite-src/$(SQLITE_AMALGAMATION)
	mkdir -p $(OBJ)
	$(EMCC) $(CFLAGS) -Isqlite-src/$(SQLITE_AMALGAMATION)/ -c $< -o $@

$(OBJ)/pthreadfs.o : $(PTHREADFS_CPP) $(PTHREADFS_H)
	mkdir -p $(OBJ)
	$(EMCC) -c $(CFLAGS) $< -o $@

$(OBJ)/%.o : $(EMTESTS)/%.cpp
	mkdir -p $(OBJ)
	$(EMCC) -c $(CFLAGS) $< -o $@

$(OBJ)/%.o : $(PRELOADTESTS)/%.cpp
	mkdir -p $(OBJ)
	$(EMCC) -c $(CFLAGS) $< -o $@

# Don't delete my precious object files
.PRECIOUS: $(OBJ)/%.out

.PHONY: sqlite-speedtest
sqlite-speedtest: dist/sqlite-speedtest/index.html
dist/sqlite-speedtest/index.html: $(OBJ)/speedtest1.o $(OBJ)/sqlite3.o $(OBJ)/pthreadfs.o $(PTHREADFS_JS) $(SQLITETESTS)/sqlite-speedtest-prejs.js
	mkdir -p dist/sqlite-speedtest
	$(EMCC) $(LINK_FLAGS) --pre-js=$(SQLITETESTS)/sqlite-speedtest-prejs.js --js-library=$(PTHREADFS_JS) $< $(word 2,$^) $(word 3,$^) -o $@ 

.PHONY: emscripten-tests
emscripten-tests: $(addprefix dist/, $(addsuffix .html, $(basename $(wildcard $(EMTESTS)/*.cpp))))
	@echo 'building emscripten-tests' $?

dist/$(EMTESTS)/%.html : $(OBJ)/%.o $(OBJ)/pthreadfs.o $(PTHREADFS_JS)
	mkdir -p dist/$(EMTESTS)
	$(EMCC) $(LINK_FLAGS) --js-library=$(PTHREADFS_JS) $< $(word 2,$^) -o $@
	

.PHONY: preload-tests
preload-tests: dist/$(PRELOADTESTS)/no_pthreadfs.html dist/$(PRELOADTESTS)/preload_pthreadfs.html

dist/$(PRELOADTESTS)/preload_files/preload_filepackage.js: $(PRELOADFILES) $(FILE_PACKAGER)
	mkdir -p dist/preload-tests/preload_files/
	python3 $(FILE_PACKAGER) $(addsuffix .data, $(basename $@)) --preload ./$(PRELOADTESTS)/input@/pthreadfs --use_pthreadfs --js-output=$@

dist/$(PRELOADTESTS)/preload_pthreadfs.html: $(OBJ)/preload.o $(OBJ)/pthreadfs.o dist/$(PRELOADTESTS)/preload_files/preload_experimental_filepackage.js $(PTHREADFS_JS)
	mkdir -p dist/preload-tests
	$(EMCC) $(LINK_FLAGS) -o $@ --js-library=$(PTHREADFS_JS)  --pre-js $(word 3,$^)  $< $(word 2,$^) 
	
dist/$(PRELOADTESTS)/no_pthreadfs.html: $(OBJ)/preload.o $(PRELOADFILES)
	mkdir -p dist/preload-tests
	$(EMCC) $(LINK_FLAGS) -o $@ --preload-file $(PRELOADTESTS)/input@/pthreadfs $<