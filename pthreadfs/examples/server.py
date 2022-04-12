from http.server import HTTPServer, SimpleHTTPRequestHandler, test
import sys
import mimetypes

class CORSRequestHandler (SimpleHTTPRequestHandler):
    def end_headers (self):
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        SimpleHTTPRequestHandler.end_headers(self)

if __name__ == '__main__':
    mimetypes.add_type('application/wasm', 'wasm', strict=True)
    test(CORSRequestHandler, HTTPServer, port=8992)