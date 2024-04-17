# This is the python script for Prometheus Perplex, aka "Plaude", stealing fire from the gods! 
# This top part is just all the boilerplate to make the flask app work.
import logging
import configparser
from typing import Iterable, Dict
from os import listdir
from uuid import uuid4
from time import sleep, time
from threading import Thread
from json import loads, dumps
from random import getrandbits
from colorama import Fore, Style
from websocket import WebSocketApp
from flask import Flask, request, jsonify, Response
from requests import Session, get, post
import tiktoken

logging.basicConfig(
    level=logging.DEBUG,
    format=f'{Fore.YELLOW}%(levelname)s{Style.RESET_ALL} - {Fore.WHITE}%(message)s{Style.RESET_ALL}'
)

config = configparser.ConfigParser()
config.read('config.ini')
email = config.get('Perplexity', 'email')

class Perplexity:
    def __init__(self, email: str = None) -> None:
        self.session: Session = Session()
        self.user_agent: dict = {"User-Agent": "Ask/2.4.1/224 (iOS; iPhone; Version 17.1) isiOSOnMac/false", "X-Client-Name": "Perplexity-iOS"}
        self.session.headers.update(self.user_agent)

        if email and ".perplexity_session" in listdir():
            self._recover_session(email)
        else:
            self._init_session_without_login()

            if email:
                self._login(email)

        self.email: str = email
        self.t: str = self._get_t()
        self.sid: str = self._get_sid()

        self.n: int = 1
        self.base: int = 420
        self.queue: list = []
        self.finished: bool = True
        self.last_uuid: str = None
        self.backend_uuid: str = None  # unused because we can't yet follow-up questions
        self.frontend_session_id: str = str(uuid4())

        while True:
            if self._ask_anonymous_user():
                break
            else:
                logging.warning("Anonymous user request failed. Attempting email login.")
                self._login(email)

        self.ws: WebSocketApp = self._init_websocket()
        self.ws_thread: Thread = Thread(target=self.ws.run_forever).start()
        self._auth_session()

        while not (self.ws.sock and self.ws.sock.connected):
            sleep(0.01)

    def _recover_session(self, email: str) -> None:
        with open(".perplexity_session", "r") as f:
            perplexity_session: dict = loads(f.read())

        if email in perplexity_session:
            self.session.cookies.update(perplexity_session[email])
        else:
            self._login(email, perplexity_session)
    
    def _login(self, email: str, ps: dict = None) -> None:
        self.session.post(url="https://www.perplexity.ai/api/auth/signin-email", data={"email": email})

        email_link: str = str(input("paste the link you received by email: "))
        self.session.get(email_link)

        if ps:
            ps[email] = self.session.cookies.get_dict()
        else:
            ps = {email: self.session.cookies.get_dict()}

        with open(".perplexity_session", "w") as f:
            f.write(dumps(ps))

    def _init_session_without_login(self) -> None:
        self.session.get(url=f"https://www.perplexity.ai/search/{str(uuid4())}")
        self.session.headers.update(self.user_agent)
    
    def _auth_session(self) -> None:
        self.session.get(url="https://www.perplexity.ai/api/auth/session")

    def _get_t(self) -> str:
        return format(getrandbits(32), "08x")

    def _get_sid(self) -> str:
        return loads(self.session.get(
            url=f"https://www.perplexity.ai/socket.io/?EIO=4&transport=polling&t={self.t}"
        ).text[1:])["sid"]

    def _ask_anonymous_user(self) -> bool:
        request_data = "40{\"jwt\":\"anonymous-ask-user\"}"
        logging.info(f"Sending anonymous user request: {request_data}")

        response = self.session.post(
            url=f"https://www.perplexity.ai/socket.io/?EIO=4&transport=polling&t={self.t}&sid={self.sid}",
            data=request_data
        ).text

        logging.info(f"Response from _ask_anonymous_user: {response}")

        if response == "OK":
            logging.info("Anonymous user request successful")
            return True
        else:
            logging.warning("Anonymous user request failed")
            return False

    def _start_interaction(self) -> None:
        self.finished = False

        if self.n == 9:
            self.n = 0
            self.base *= 10
        else:
            self.n += 1

        self.queue = []

    def _get_cookies_str(self) -> str:
        cookies = ""
        for key, value in self.session.cookies.get_dict().items():
            cookies += f"{key}={value}; "
        return cookies[:-2]
    
    def _write_file_url(self, filename: str, file_url: str) -> None:
        if ".perplexity_files_url" in listdir():
            with open(".perplexity_files_url", "r") as f:
                perplexity_files_url: dict = loads(f.read())
        else:
            perplexity_files_url: dict = {}

        perplexity_files_url[filename] = file_url

        with open(".perplexity_files_url", "w") as f:
            f.write(dumps(perplexity_files_url))

    def _init_websocket(self) -> WebSocketApp:
        def on_open(ws: WebSocketApp) -> None:
            ws.send("2probe")
            ws.send("5")

        def on_message(ws: WebSocketApp, message: str) -> None:
            if message == "2":
                ws.send("3")
            elif not self.finished:
                if message.startswith("42"):
                    message : list = loads(message[2:])
                    content: dict = message[1]
                    if "mode" in content and content["mode"] == "copilot":
                        content["copilot_answer"] = loads(content["text"])
                    elif "mode" in content:
                        content.update(loads(content["text"]))
                    content.pop("text")
                    if ("final" in content and content["final"]) or ("status" in content and content["status"] == "completed"):
                        self.finished = True
                    self.queue.append(content)
                    if message[0] == "query_answered":
                        self.last_uuid = content["uuid"]
                elif message.startswith("43"):
                    message: dict = loads(message[3:])[0]
                    if ("uuid" in message and message["uuid"] != self.last_uuid) or "uuid" not in message:
                        self.queue.append(message)
                        self.finished = True

        return WebSocketApp(
            url=f"wss://www.perplexity.ai/socket.io/?EIO=4&transport=websocket&sid={self.sid}",
            header=self.user_agent,
            cookie=self._get_cookies_str(),
            on_open=on_open,
            on_message=on_message,
            on_error=lambda ws, err: print(f"websocket error: {err}")
        )
    
    def _s(self, query: str, mode: str = "concise", search_focus: str = "internet", attachments: list[str] = [], language: str = "en-GB", in_page: str = None, in_domain: str = None) -> None:
        assert self.finished, "already searching"
        assert mode in ["concise", "copilot"], "invalid mode"
        assert len(attachments) <= 4, "too many attachments: max 4"
        assert search_focus in ["internet", "scholar", "writing", "wolfram", "youtube", "reddit"], "invalid search focus"

        if in_page:
            search_focus = "in_page"
        if in_domain:
            search_focus = "in_domain"

        self._start_interaction()
        ws_message: str = f"{self.base + self.n}" + dumps([
            "perplexity_ask",
            query,
            {
                "version": "2.1",
                "source": "default", # "ios"
                "frontend_session_id": self.frontend_session_id,
                "language": language,
                "timezone": "CET",
                "attachments": attachments,
                "search_focus": search_focus,
                "frontend_uuid": str(uuid4()),
                "mode": mode,
                # "use_inhouse_model": True
                "in_page": in_page,
                "in_domain": in_domain
            }
        ])

        self.ws.send(ws_message)

    def search(self, query: str, mode: str = "concise", search_focus: str = "internet", attachments: list[str] = [], language: str = "en-GB", timeout: float = 30, in_page: str = None, in_domain: str = None) -> Iterable[Dict]:
        self._s(query, mode, search_focus, attachments, language, in_page, in_domain)

        start_time: float = time()
        while (not self.finished) or len(self.queue) != 0:
            if timeout and time() - start_time > timeout:
                self.finished = True
                logging.warning("Search timed out")
                return {"error": "timeout"}
            if len(self.queue) != 0:
                yield self.queue.pop(0)

    def search_sync(self, query: str, mode: str = "concise", search_focus: str = "internet", attachments: list[str] = [], language: str = "en-GB", timeout: float = 30, in_page: str = None, in_domain: str = None) -> dict:
        logging.info(f"Starting synchronous search with query: {query}")
        self._s(query, mode, search_focus, attachments, language, in_page, in_domain)

        start_time: float = time()
        while not self.finished:
            if timeout and time() - start_time > timeout:
                self.finished = True
                logging.warning("Synchronous search timed out")
                return {"error": "timeout"}
        
        return self.queue.pop(-1)

    def upload(self, filename: str) -> str:
        assert self.finished, "already searching"
        assert filename.split(".")[-1] in ["txt", "pdf"], "invalid file format"

        if filename.startswith("http"):
            file = get(filename).content
        else:
            with open(filename, "rb") as f:
                file = f.read()

        self._start_interaction()
        ws_message: str = f"{self.base + self.n}" + dumps([
            "get_upload_url",
            {
                "version": "2.1",
                "source": "default",
                "content_type": "text/plain" if filename.split(".")[-1] == "txt" else "application/pdf",
            }
        ])

        self.ws.send(ws_message)

        while not self.finished or len(self.queue) != 0:
            if len(self.queue) != 0:
                upload_data = self.queue.pop(0)

        assert not upload_data["rate_limited"], "rate limited"
        
        post(
            url=upload_data["url"],
            files={
                "acl": (None, upload_data["fields"]["acl"]),
                "Content-Type": (None, upload_data["fields"]["Content-Type"]),
                "key": (None, upload_data["fields"]["key"]),
                "AWSAccessKeyId": (None, upload_data["fields"]["AWSAccessKeyId"]),
                "x-amz-security-token": (None, upload_data["fields"]["x-amz-security-token"]),
                "policy": (None, upload_data["fields"]["policy"]),
                "signature": (None, upload_data["fields"]["signature"]),
                "file": (filename, file)
            }
        )

        file_url: str = upload_data["url"] + upload_data["fields"]["key"].split("$")[0] + filename

        self._write_file_url(filename, file_url)

        return file_url
    
    def threads(self, query: str = None, limit: int = None) -> list[dict]:
        assert self.email, "not logged in"
        assert self.finished, "already searching"

        if not limit: limit = 20
        data: dict = {"version": "2.1", "source": "default", "limit": limit, "offset": 0}
        if query: data["search_term"] = query

        self._start_interaction()
        ws_message: str = f"{self.base + self.n}" + dumps([
            "list_ask_threads",
            data
        ])

        self.ws.send(ws_message)

        while not self.finished or len(self.queue) != 0:
            if len(self.queue) != 0:
                return self.queue.pop(0)
            
    def list_autosuggest(self, query: str = "", search_focus: str = "internet") -> list[dict]:
        assert self.finished, "already searching"

        self._start_interaction()
        ws_message: str = f"{self.base + self.n}" + dumps([
            "list_autosuggest",
            query,
            {
                "has_attachment": False,
                "search_focus": search_focus,
                "source": "default",
                "version": "2.1"
            }
        ])

        self.ws.send(ws_message)

        while not self.finished or len(self.queue) != 0:
            if len(self.queue) != 0:
                return self.queue.pop(0)
    
    def close(self) -> None:
        self.ws.close()

        if self.email:
            with open(".perplexity_session", "r") as f:
                perplexity_session: dict = loads(f.read())

            perplexity_session[self.email] = self.session.cookies.get_dict()

            with open(".perplexity_session", "w") as f:
                f.write(dumps(perplexity_session))
#End of boilerplate Perplexity Class

#Here we define some useful functions for the Prometheus app. Inspired by Slaude! 
def convert_sillytavern_to_plaintext(messages):
    plaintext = ""
    system_messages = ""
    for message in messages:
        if message["role"] == "user":
            plaintext += f"Human: {message['content']}\n"
        elif message["role"] == "assistant":
            plaintext += f"Assistant: {message['content']}\n"
        elif message["role"] == "system":
            system_messages += f"{message['content']}\n"
    return plaintext, system_messages

def convert_plaintext_to_sillytavern(response):
    return {
        "choices": [
            {
                "delta": {
                    "content": response
                }
            }
        ]
    }

def convert_plaintext_to_sillytavern_error(error_message):
    return {
        "error": {
            "message": error_message
        }
    }

# Actual inference code
app = Flask(__name__)
@app.route('/chat/completions', methods=['POST'])
def perplexity_api():
    data = request.get_json()
    messages = data['messages']
    logging.info(f"Raw message from SillyTavern can be found in SillyTavern's Log.")
    
    # Convert SillyTavern messages to plain text
    plaintext_question, system_messages = convert_sillytavern_to_plaintext(messages)
    
    # Initialize the Perplexity object
    perplexity = Perplexity(email)
    
    # Initialize the tiktoken tokenizer with the GPT-4 encoding
    tokenizer = tiktoken.encoding_for_model("gpt-4")
    
    # Calculate the number of tokens in the plaintext_question
    num_tokens = len(tokenizer.encode(plaintext_question))
    logging.info(f"Number of tokens: {Fore.GREEN}{num_tokens}{Style.RESET_ALL}")
    
    if num_tokens > 10500:
        error_message = "This endpoint does not support requests over 10.5k tokens. Please reduce your tokens sent."
        sillytavern_error_response = convert_plaintext_to_sillytavern_error(error_message)
        return jsonify(sillytavern_error_response), 400

    # Perform a search with the focus set to "writing" and the plaintext_question
    answer = perplexity.search(plaintext_question, search_focus="writing")
    
    # Initialize variables to keep track of streamed words
    streamed_words = ""
    prev_response_length = 0
    
    def stream():
        nonlocal streamed_words, prev_response_length
        response_buffer = ""
        
        for a in answer:
            if "answer" in a:
                current_streamed_words = a["answer"].replace(" ", " ")
                
                # Check if "Human: " is encountered in the current streamed words
                human_index = current_streamed_words.find("Human: ")
                if human_index != -1:
                    logging.info("Encountered 'Human: ' in the answer. Trimming the answer.")
                    # Trim the answer up to "Human: "
                    current_streamed_words = current_streamed_words[:human_index].strip()
                    # Update streamed_words with the trimmed answer
                    streamed_words = current_streamed_words
                    new_content = streamed_words[prev_response_length:]
                    prev_response_length = len(streamed_words)
                    print(f"{Fore.GREEN}{new_content}{Style.RESET_ALL}", end="", flush=True)
                    sillytavern_response = convert_plaintext_to_sillytavern(new_content)
                    yield f"data: {dumps(sillytavern_response)}\n\n"
                    
                    # Close the Perplexity object when "Human: " is encountered
                    perplexity.close()
                    # Terminate the answer streaming
                    break
                else:
                    streamed_words = current_streamed_words
                    new_content = streamed_words[prev_response_length:]
                    prev_response_length = len(streamed_words)
                    print(f"{Fore.GREEN}{new_content}{Style.RESET_ALL}", end="", flush=True)
                    sillytavern_response = convert_plaintext_to_sillytavern(new_content)
                    yield f"data: {dumps(sillytavern_response)}\n\n"
            
            if a.get("final", False) or a.get("status") == "completed":
                print("\n", end="", flush=True) # Print a newline character
                logging.info("Search completed")
                # Close the Perplexity object when the response is finished
                perplexity.close()
                break
    
    return Response(stream(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(port=5001)
