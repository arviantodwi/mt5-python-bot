# Project Context: Trading Bot

## 1. Project Overview

- **Goal:** Build a trading bot connected to MetaTrader5, using Python.
- **Core Features:** Automated trading, real-time market data retrieval, and future AI integration.

## 2. Tech Stack

- **Language:** Python
- **Package Manager:** Pip
- **MetaTrader5 Library:** mt5_wrapper
- **Testing:** pytest

## 3. Project Structure

- `app`: Core source code.
- `tests`: All test scripts.

## 4. Key Commands

- `python main.py`: Run the bot.
- `pytest .\tests`: Run tests.

## 5. Coding Conventions

<!-- If you have specific coding rules, list them here. -->

- **Imports:** Place imports inside functions or at the top of the file, depending on their scope. Use top-level imports only when they are shared across multiple functions.
- **Comments:** Add docstring comments to describe each function’s purpose. Include inline comments when they help clarify complex logic or specific code behavior.
- **Testing:** For any new code added to the `app` directory, write corresponding tests to maintain high test coverage and ensure reliability.

## 6. Current Goals

- **What I'm working on:** Integrate MetaTrader5 to get live price data and execute automated trades based on defined strategy rules.
