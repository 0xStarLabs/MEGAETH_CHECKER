import aiohttp
import asyncio
from loguru import logger
import sys
import csv
from datetime import datetime
from eth_account import Account
import random
from config import USE_ADDRESS_FILE, THREADS, PAUSES, SHUFFLE


# Logging configuration
logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<light-cyan>{time:HH:mm:ss:SSS}</light-cyan> | <level>{level: <8}</level> | <white>{file}:{line}</white> | <white>{message}</white>",
)
logger.add(
    "data/logs/app.log",
    rotation="100 MB",
    format="{time:YYYY-MM-DD HH:mm:ss:SSS} | {level: <8} | {file}:{line} | {message}",
    encoding="utf-8",
)

def load_addresses():
    if USE_ADDRESS_FILE:
        with open("data/addresses.txt", "r") as file:
            return [line.strip() for line in file.readlines() if line.strip()]
    else:
        with open("data/private_keys.txt", "r") as file:
            private_keys = [line.strip() for line in file.readlines() if line.strip()]
            addresses = []
            for pk in private_keys:
                try:
                    account = Account.from_key(pk)
                    addresses.append(account.address)
                except Exception as e:
                    logger.error(f"Error converting private key to address: {e}")
            return addresses

def load_proxies(num_addresses):
    try:
        with open("data/proxies.txt", "r") as file:
            proxies = [line.strip() for line in file.readlines() if line.strip()]
            
        if not proxies:
            return [None] * num_addresses
        
        while len(proxies) < num_addresses:
            proxies.append(random.choice(proxies))
            
        if len(proxies) > num_addresses:
            proxies = proxies[:num_addresses]
            
        return proxies
    except FileNotFoundError:
        logger.warning("proxies.txt not found, continuing without proxies")
        return [None] * num_addresses

class MegaEthChecker:
    def __init__(self):
        self.session = None
        self.whitelisted_addresses = []
        self.headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'referer': 'https://nft.megaeth.com/login',
        }
        self.semaphore = asyncio.Semaphore(THREADS)

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def check_address(self, check_index, original_index, address, proxy=None):
        async with self.semaphore:  # Limit concurrent requests
            # Random pause before starting new thread
            pause_time = random.randint(PAUSES[0], PAUSES[1])
            logger.info(f"Waiting {pause_time} seconds before checking address {check_index} - {original_index}")
            await asyncio.sleep(pause_time)
            
            try:
                params = {'address': address}
                proxy_url = f"http://{proxy}" if proxy else None
                
                async with self.session.get(
                    "https://nft.megaeth.com/api/whitelist",
                    params=params,
                    proxy=proxy_url
                ) as response:
                    data = await response.json()
                    is_whitelisted = data.get('isWhitelisted', False)

                    status = "WHITELISTED" if is_whitelisted else "NOT WHITELISTED"
                    proxy_info = f" | Proxy: {proxy}" if proxy else ""
                    logger.info(f"{check_index} - {original_index} | Address: {address} | Status: {status}{proxy_info}")

                    if is_whitelisted:
                        self.whitelisted_addresses.append(address)

            except Exception as e:
                logger.error(f"{check_index} - {original_index} | Error checking address {address} with proxy {proxy}: {e}")

    async def check_all(self, addresses, proxies):
        # Create list of tuples with original indices
        check_data = list(enumerate(zip(addresses, proxies), 1))
        
        if SHUFFLE:
            random.shuffle(check_data)
        
        tasks = [
            self.check_address(
                check_index=i+1,
                original_index=original_idx,
                address=address,
                proxy=proxy
            )
            for i, (original_idx, (address, proxy)) in enumerate(check_data)
        ]
        await asyncio.gather(*tasks)
        return self.whitelisted_addresses

async def main():
    addresses = load_addresses()
    proxies = load_proxies(len(addresses))
    
    async with MegaEthChecker() as checker:
        whitelisted = await checker.check_all(addresses, proxies)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"data/whitelist_results_{timestamp}.csv"
    
    with open(filename, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Address'])  # Header
        writer.writerows([[address] for address in whitelisted])
    
    logger.info(f"Total whitelisted addresses: {len(whitelisted)}")
    logger.info("Whitelisted addresses:")
    for i, address in enumerate(whitelisted, 1):
        logger.info(f"{i} | Address: {address}")
    logger.info(f"Results saved to {filename}")

if __name__ == "__main__":
    asyncio.run(main())

