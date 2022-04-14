#include <stdio.h>
#include <stdlib.h>
#include <sqlite3.h>
#include <pthread.h>

int callback(void *NotUsed, int argc, char **argv, char **azColName){
  int i;
  for(i=0; i<argc; i++){
    printf("%s = %s\n", azColName[i], argv[i] ? argv[i] : "NULL");
  }
  printf("\n");
  return 0;
}

void *query_database_internal( char *ptr ) {
    char *query;
    query = (char *) ptr;

    printf("%s\n", query);

    char *zErrMsg = 0;
    sqlite3 *db;
    int rc;

    rc = sqlite3_open("persistent/db_test", &db);

    printf("open response: %d\n", query);

    if( rc ){
        fprintf(stderr, "Can't open database: %s\n", sqlite3_errmsg(db));
        sqlite3_close(db);
        exit(1);
        return 1;
    }

    rc = sqlite3_exec(db, *query, callback, 0, &zErrMsg);
    printf("exec response: %d\n", rc);
    if( rc != SQLITE_OK ){
        fprintf(stderr, "SQL error: %s\n", zErrMsg);
        sqlite3_free(zErrMsg);
        exit(1);
        return 1;
    }

    sqlite3_close(db);
    return 0;
}

int query_database(char *query) {
    pthread_t thread;
    pthread_create(&thread, NULL, query_database_internal, (void*) query);
    return 0;
}
