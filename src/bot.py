# ==================== Main Entry Point ====================
async def main():
    """Main async function"""
    global bot_instance
    
    # Create bot instance
    bot_token = BOT_TOKEN
    if bot_token == "YOUR_BOT_TOKEN_HERE" or not bot_token:
        logger.error("Please set BOT_TOKEN environment variable")
        return
    
    # Initialize bot
    bot_instance = UsernameMonitorBot(bot_token)
    
    # Run bot - ye important hai
    await bot_instance.initialize()
    await bot_instance.app.initialize()
    await bot_instance.app.start()
    await bot_instance.app.updater.start_polling()
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopping bot...")
    finally:
        if bot_instance.monitoring_task:
            bot_instance.monitoring_task.cancel()
        await bot_instance.app.updater.stop()
        await bot_instance.app.stop()
        await bot_instance.app.shutdown()

def run_bot():
    """Run bot in asyncio event loop"""
    try:
        asyncio.run(main())
    except RuntimeError as e:
        logger.error(f"Runtime error: {e}")
        # Agar event loop already running hai to
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())

if __name__ == "__main__":
    # Logging setup
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run bot
    run_bot()
    
    # Keep main thread alive
    while True:
        try:
            time.sleep(60)
        except KeyboardInterrupt:
            break
