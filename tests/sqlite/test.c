/*
 * Copyright 2011 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */

#include <stdio.h>
#include <stdlib.h>
#include <sqlite3.h>

static int callback(void *NotUsed, int argc, char **argv, char **azColName){
  int i;
  for(i=0; i<argc; i++){
    printf("%s = %s\n", azColName[i], argv[i] ? argv[i] : "NULL");
  }
  printf("\n");
  return 0;
}

int main(){
  sqlite3 *db;
  char *zErrMsg = 0;
  int rc;
  int i;
  const char *commands[] = {
    "CREATE TABLE bulk_actions (id TEXT PRIMARY KEY NOT NULL, json TEXT NOT NULL)",
    "CREATE TABLE calendar_accounts (email TEXT NOT NULL, sync_token TEXT, UNIQUE(email))",
    "CREATE TABLE calendars (id TEXT NOT NULL, account TEXT NOT NULL, name TEXT NOT NULL, json TEXT, page_token TEXT, sync_token TEXT, last_request_at INTEGER, page_count INTEGER, UNIQUE(account, id))",
    "CREATE TABLE contacts (id TEXT NOT NULL, name TEXT, json TEXT, email TEXT NOT NULL, score REAL, score_data TEXT, likely_non_person BOOL DEFAULT 0, UNIQUE(id, email))",
    "CREATE TABLE events (calendar_id TEXT NOT NULL, google_id TEXT NOT NULL, ical_id TEXT, summary TEXT, start_time INTEGER NOT NULL, end_time INTEGER, all_day INTEGER NOT NULL, json TEXT, UNIQUE(calendar_id, google_id))",
    "CREATE TABLE general (key TEXT PRIMARY KEY NOT NULL, json TEXT NOT NULL)",
    "CREATE TABLE labels (id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL, slug TEXT, type TEXT)",
    "CREATE TABLE list_ids (list_id TEXT NOT NULL, thread_id TEXT NOT NULL, sort INTEGER, unique(list_id, thread_id))",
    "CREATE TABLE lists (id TEXT PRIMARY KEY NOT NULL, page_token TEXT, min_sort int, delta_token TEXT, catch_up_last_modified_datetime INTEGER)",
    "CREATE TABLE messages (id TEXT PRIMARY KEY NOT NULL, timestamp INTEGER, is_sent INTEGER, emails TEXT NOT NULL, json TEXT, thread_id TEXT)",
    "CREATE TABLE modifiers (id INTEGER PRIMARY KEY, name TEXT, queue_name TEXT NOT NULL, json TEXT NOT NULL, session_id TEXT, replace_id TEXT, created_at INTEGER, updated_at INTEGER, started_at INTEGER, completed_at INTEGER)",
    "CREATE TABLE profiles (email TEXT PRIMARY KEY NOT NULL, insights TEXT, threads TEXT, twitter TEXT)",
    "CREATE TABLE sync (id TEXT PRIMARY KEY NOT NULL, value TEXT)",
    "CREATE TABLE threads (thread_id TEXT PRIMARY KEY NOT NULL, json TEXT, sort INTEGER, in_spam_trash BOOLEAN, has_attachments BOOLEAN, superhuman_data TEXT, needs_render INTEGER DEFAULT 1)",
    "CREATE INDEX calendar_accounts_email ON calendar_accounts (email)",
    "CREATE INDEX calendars_account_id ON calendars (account, id)",
    "CREATE INDEX contacts_score ON contacts (score)",
    "CREATE INDEX events_calendar_id_start_time_end_time ON events (calendar_id, start_time, end_time)",
    "CREATE INDEX list_ids_list_id_sort ON list_ids (list_id, sort)",
    "CREATE INDEX list_ids_thread_id ON list_ids (thread_id)",
    "CREATE INDEX modifiers_completed_at ON modifiers (completed_at)",
    "CREATE INDEX modifiers_queue_name ON modifiers (queue_name)",
    "CREATE INDEX threads_needs_render ON threads (needs_render)",
    "CREATE INDEX threads_sort ON threads (sort)",

    "INSERT INTO labels VALUES(1,'test','test', 'test');",
    "SELECT * FROM labels;",
    NULL
  };

  rc = sqlite3_open("persistent/db_test", &db);
  if( rc ){
    fprintf(stderr, "Can't open database: %s\n", sqlite3_errmsg(db));
    sqlite3_close(db);
    exit(1);
  }
  for (i = 0; commands[i]; i++) {
    rc = sqlite3_exec(db, commands[i], callback, 0, &zErrMsg);
    if( rc!=SQLITE_OK ){
      fprintf(stderr, "SQL error on %d: %s\n", i, zErrMsg);
      sqlite3_free(zErrMsg);
      exit(1);
    }
  }
  sqlite3_close(db);
  return 0;
}
