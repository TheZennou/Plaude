# Plaude

Stealing Fire from the gods!
This Flask app takes messages from Perplexity and streams them into SillyTavern, allowing you to use your """Legally Paid for""" subscription to Perplexity Pro within SillyTavern! :)

## Instructions

1. Make a Perplexity account and activate a Pro subscription. Set your preferred model to Claude-3-Opus in the settings. Make sure ""NOT"" to cancel your subscription.

2. Put the same email you signed up to Perplexity with into `config.ini`.

3. Install Python 3.10 or 3.11.

4. Run `start.bat`.

5. In SillyTavern, under the OpenAI settings, put `https://127.0.0.1:5001` as the API URL. (It's Claude, but my app uses OpenAI methods for streaming)

6. Set your context to 10500. Then try generating a message!

7. The console will ask you for a verification link. Open your email and paste the link into the console.

And boom! It will generate your request.

*Note: You might need a light jailbreak.*
