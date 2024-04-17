# Plaude

Stealing Fire from the gods!
This Flask app takes messages from Perplexity and streams them into SillyTavern, allowing you to use your """Legally Paid for""" subscription to Perplexity Pro within SillyTavern! :)

## Instructions
1. Click the green <> Code button, and download the repo as a ZIP file, extract it somewhere.

2. Make a Perplexity account and activate a Pro subscription. Set your preferred model to Claude-3-Opus in the settings. Make sure ""NOT"" to cancel your subscription.

3. Put the same email you signed up to Perplexity with into `config.ini`.

4. Install Python 3.10 or 3.11.

5. Run `start.bat`.

6. In SillyTavern, under the OpenAI settings, put `https://127.0.0.1:5001` as the API URL. (It's Claude, but my app uses OpenAI methods for streaming)

7. Set your context to 10500. Then try generating a message!

8. The console will ask you for a verification link. Open your email and paste the link into the console.

And boom! It will generate your request.

*Note: You might need a light jailbreak.*
