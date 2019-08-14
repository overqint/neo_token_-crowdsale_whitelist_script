"""
Based on https://github.com/NarrativeCompany/tokensale-neo-smartcontract/blob/master/util/neo-nrve-eventhandler.py

Usage:
* Update config/neo-nrve-config.json params
* Update config/network-wallets.json wallet path for the selected network
* Update config/db-config.json database details

python3.5 -m venv venv
source venv/bin/activate

Only need to be done once
pip install -U setuptools pip wheel
pip install -e .

python3 whitelistEventHandler.py

"""
import os
import json
import argparse
from time import sleep

from neo.Core.Blockchain import Blockchain

from neo.contrib.smartcontract import SmartContract
from neo.SmartContract.ContractParameter import ContractParameter, ContractParameterType

from main import BlockchainMain, NetworkType

import pymysql.cursors
from pymysql import MySQLError

# WhitelistEventHandler that is extending the BlockchainMain class
class WhitelistEventHandler(BlockchainMain):
    smart_contract_hash = None

    # Setup the smart contract instance
    smart_contract = None

    # load database configuration
    db_config = None

    # will be set to True if the wallets needs a recovery
    wallet_needs_recovery = False

    # neo addresses array that will be whitelisted
    whitelists_to_process = []

    # store the last transaction hash
    whitelist_tx_processing = None

    # wait X seconds for transaction to be persisted on the blockchain
    wait_whitelist_tx_processing_seconds = None

    # in X seconds process the next batch of addresses
    wait_load_addresses_to_whitelist_seconds = None

    # address count that will be processed in one transaction
    addresses_to_whitelist_count = None

    def __init__(self):

        with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config', 'neo-nrve-config.json'),
                  'r') as f:
            config = json.load(f)

        with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config', 'network-wallets.json'),
                  'r') as f:
            network_wallets_config = json.load(f)

        with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config', 'db-config.json'), 'r') as f:
            self.db_config = json.load(f)

        super().__init__(NetworkType[config['network']], 'neo-nrve-eventhandler')

        self.smart_contract_hash = config['smart_contract']
        self.smart_contract = SmartContract(self.smart_contract_hash)

        self.wait_whitelist_tx_processing_seconds = config['wait_whitelist_tx_processing_seconds']
        self.wait_load_addresses_to_whitelist_seconds = config['wait_load_addresses_to_whitelist_seconds']

        self.addresses_to_whitelist_count = config['addresses_to_whitelist_count']

        self.setup_wallet(network_wallets_config[config['network']]['wallet_path'])

    """
    infinite loop that reads constantly from the database the addresses that need to be whitelisted
    and sends them to the smart contract
    
    on every loop it sleeps for 1 second and increments its counter
    
    other logic in the loop works with the modulo operator 
    and can determine on what mod seconds it wants to trigger certain operations like 
    - waiting for the transaction
    - loading neo addresses to be whitelisted
    
    if there are no neo addresses to be whitelisted the loop skips the processes that come after this check
    
    if the smart contract is invoked successfully neo addresses in the database are marked as whitelisted
    
    else it tries to rebuild the wallet, selects from the database addresses that are not whitelisted and resumes the whitelisting process

    """
    def whitelist_addresses(self):
        self.logger.info("whitelist_addresses...")
        count = 0
        while True:
            sleep(1)
            count += 1

            # every 2 seconds print the block hight
            if (count % 2) == 0:
                self.logger.info("Block %s / %s", str(Blockchain.Default().Height),
                                 str(Blockchain.Default().HeaderHeight))

            # keep waiting until the last whitelist transaction comes through for X (see neo-nrve-config.json) seconds,
            # then set whitelist_tx_processing to None so the process can continue
            if self.whitelist_tx_processing:
                if (count % self.wait_whitelist_tx_processing_seconds) != 0:
                    self.whitelist_tx_processing = None
                self.logger.debug('whitelist tx processing: %s', self.whitelist_tx_processing)
                continue

            # load addresses to whitelist every X (see neo-nrve-config.json) seconds, but only if the list is empty
            if not self.whitelists_to_process:
                # look for NEO addresses to whitelist every 5 seconds
                if (count % self.wait_load_addresses_to_whitelist_seconds) != 0:
                    continue
                self.load_addresses_to_whitelist()

            # no whitelists to process? then keep waiting
            if not self.whitelists_to_process:
                continue

            # if the wallet is out of sync on the testnet or mainnet it could take a really long time to sync it
            if self.wallet_needs_recovery:
                self.logger.debug('recovering wallet...')
                self.recover_wallet()
                self.wallet_needs_recovery = False
            else:
                self.logger.debug('syncing wallet...')
                self.wallet_sync()

            addresses_to_whitelist = self.whitelists_to_process[0:self.addresses_to_whitelist_count]
            self.whitelists_to_process = self.whitelists_to_process[self.addresses_to_whitelist_count:]

            self.logger.debug('trying to whitelist addresses: %s', addresses_to_whitelist)
            result, result_string = self.test_invoke(
                [self.smart_contract_hash, 'crowdsale_register', addresses_to_whitelist],
                len(addresses_to_whitelist), False)
            self.logger.debug('smart contract invoked; whitelisting addresses result raw: %s', result)
            self.logger.debug('smart contract invoked; whitelisting addresses result as string: %s', result_string)

            if not result_string:
                self.logger.info("transaction result empty,  wallet could be out of sync recover it and try again")
                self.wallet_needs_recovery = True

            elif result_string and result:
                self.logger.info("transaction relayed")
                self.whitelist_tx_processing = result.Hash
                self.logger.debug('successfully whitelisted addresses: %s', addresses_to_whitelist)
                self.mark_address_as_whitelisted(addresses_to_whitelist)
                # self.check_whitelisted_address(addresses_to_whitelist)

    # connection to the mysql/mariadb server
    def get_connection(self):
        # Connect to the database
        return pymysql.connect(host=self.db_config['host'],
                               user=self.db_config['user'],
                               password=self.db_config['password'],
                               db=self.db_config['db'],
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor)

    # check the crowdsale status of the given addresses
    def check_whitelisted_address(self, addresses_to_whitelist):
        if addresses_to_whitelist:
            result, result_string = self.test_invoke(
                [self.smart_contract_hash, 'crowdsale_status', addresses_to_whitelist],
                len(addresses_to_whitelist), False)
            self.logger.debug('check whitelisted address result: %s', result_string)
        else:
            self.logger.error('no addresses to mark as whitelisted in the DB supplied')

    # connect to the database and load the addresses from NvmUser table that are not marked as whitelisted
    def load_addresses_to_whitelist(self):
        connection = self.get_connection()
        try:
            with connection.cursor() as cursor:
                sql = "select neo_address FROM NvmUser WHERE crowdsale_register = 0 LIMIT %s ;"
                args = (self.addresses_to_whitelist_count)
                cursor.execute(sql, args)

                rows = cursor.fetchall()
                # print(rows)

                for row in rows:
                    self.whitelists_to_process.append(str(row['neo_address']))

                self.logger.debug('loaded addresses to whitelist: %s', self.whitelists_to_process)
        except MySQLError as e:
            self.logger.error('ERROR: selecting whitelist addresses: {!r}, errno is {}'.format(e, e.args[0]))
        finally:
            connection.close()

    # connect to the database and mark the neo addresses as whitelisted in the NvmUser table
    def mark_address_as_whitelisted(self, addresses_to_whitelist):
        if addresses_to_whitelist:
            # addresses_to_whitelist_quoted_string = ', '.join('[("{0}")]'.format(w) for w in addresses_to_whitelist)
            connection = self.get_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.executemany("UPDATE NvmUser SET crowdsale_register = 1 WHERE neo_address = %s ",
                                       addresses_to_whitelist)
                    connection.commit()
                    self.logger.debug('last executed query for whitelisting: %s', str(cursor._last_executed));
                    self.logger.debug('DB rows updated: %s', str(cursor.rowcount));
            except MySQLError as e:
                self.logger.error('ERROR: updating whitelist address: {!r}, errno is {}'.format(e, e.args[0]))
            finally:
                connection.close()
        else:
            self.logger.error('no addresses to mark as whitelisted supplied')


def main():
    event_handler = WhitelistEventHandler()
    event_handler.run()


if __name__ == "__main__":
    main()
