import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from .advanced_language_engine import AdvancedLanguageEngine

class RequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/process':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                body = json.loads(post_data.decode('utf-8'))
                input_text = body.get('input', '')
                opts = body.get('options', {})
                engine = AdvancedLanguageEngine()
                result = engine.process_language(input_text, opts)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def serve(port: int = 8080):
    server = HTTPServer(('localhost', port), RequestHandler)
    print(f'[Seraphina AGI] HTTP API listening on {port} (POST /process)')
    server.serve_forever()

def main():
    parser = argparse.ArgumentParser(description='Seraphina AGI Companion')
    parser.add_argument('command', choices=['serve', 'process'], help='Command to run')
    parser.add_argument('--port', type=int, default=8080, help='Port for serve')
    parser.add_argument('--input', help='Input text for process')

    args = parser.parse_args()

    if args.command == 'serve':
        serve(args.port)
    elif args.command == 'process':
        if not args.input:
            print('Error: --input required for process')
            return
        engine = AdvancedLanguageEngine()
        result = engine.process_language(args.input)
        print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()