"""
Based off of: https://github.com/CityOfZion/neo-python/blob/master/examples/smart-contract.py

Example of running a NEO node and receiving notifications when events
of a specific smart contract happen.

Events include Runtime.Notify, Runtime.Log, Storage.*, Execution.Success
and several more. See the documentation here:

http://neo-python.readthedocs.io/en/latest/smartcontracts.html

Usage:
* Update config/neo-nrve-config.json params
* Update config/network-wallets.json wallet path for the selected network
* Update config/db-config.json database details

python3.5 -m venv venv
source venv/bin/activate
# bl: these only need to be done once
#pip install -U setuptools pip wheel
#pip install -e .
python neo/contrib/neo-nrve-eventhandler.py

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
import pprint


class WhitelistEventHandler(BlockchainMain):
    smart_contract_hash = None

    # Setup the smart contract instance
    smart_contract = None

    db_config = None

    ignore_blocks_older_than = None

    wallet_needs_recovery = False

    whitelists_to_process = []

    whitelist_tx_processing = None

    wait_whitelist_tx_processing_seconds = 5

    wait_load_addresses_to_whitelist_seconds = 5

    addresses_to_whitelist_count = 6

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

        self.ignore_blocks_older_than = config['ignore_blocks_older_than']

        self.wait_whitelist_tx_processing_seconds = config['wait_whitelist_tx_processing_seconds']
        self.wait_load_addresses_to_whitelist_seconds = config['wait_load_addresses_to_whitelist_seconds']

        self.addresses_to_whitelist_count = config['addresses_to_whitelist_count']

        # if not disable_auto_whitelist:
        #     self.setup_wallet(network_wallets_config[config['network']]['wallet_path'])
        # else:
        #     self.setup_network()

        self.setup_wallet(network_wallets_config[config['network']]['wallet_path'])



    def whitelist_addresses(self):
        self.logger.info("whitelist_addresses...")
        count = 0
        while True:
            sleep(3)

            count += 1

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

            if self.wallet_needs_recovery:
                self.recover_wallet()
                self.wallet_needs_recovery = False
            else:
                self.wallet_sync()

            addresses_to_whitelist = self.whitelists_to_process[0:self.addresses_to_whitelist_count]
            self.whitelists_to_process = self.whitelists_to_process[self.addresses_to_whitelist_count:]

            self.logger.debug('trying to whitelist addresses: %s', addresses_to_whitelist)
            result, result_string = self.test_invoke(
                [self.smart_contract_hash, 'crowdsale_register', addresses_to_whitelist],
                len(addresses_to_whitelist), False)
            self.logger.debug('whitelisting addresses result raw: %s', result)
            self.logger.debug('whitelisting addresses result string: %s', result_string)

            if not result_string:
                self.logger.info("transaction result empty, recover wallet and try again")
                self.wallet_needs_recovery = True
                # we need to try to process this refund again, so add it back in to the list
                # self.whitelists_to_process = addresses_to_whitelist + self.whitelists_to_process
            elif result_string and result:
                self.logger.info("transaction relayed")
                self.whitelist_tx_processing = result.Hash
                self.logger.debug('successfully whitelisted addresses: %s', addresses_to_whitelist)
                self.mark_address_as_whitelisted(addresses_to_whitelist)
                # self.check_whitelisted_address(addresses_to_whitelist)

    def get_connection(self):
        # Connect to the database
        return pymysql.connect(host=self.db_config['host'],
                               user=self.db_config['user'],
                               password=self.db_config['password'],
                               db=self.db_config['db'],
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor)

    def check_whitelisted_address(self, addresses_to_whitelist):
        if addresses_to_whitelist:
            result, result_string = self.test_invoke(
                [self.smart_contract_hash, 'crowdsale_status', addresses_to_whitelist],
                len(addresses_to_whitelist), False)
            self.logger.debug('check whitelisted address result: %s', result_string)
        else:
            self.logger.error('no addresses to mark as whitelisted in the DB supplied')

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

    def mark_address_as_whitelisted(self, addresses_to_whitelist):
        if addresses_to_whitelist:
            # addresses_to_whitelist_quoted_string = ', '.join('[("{0}")]'.format(w) for w in addresses_to_whitelist)
            connection = self.get_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.executemany("UPDATE NvmUser SET crowdsale_register = 1 WHERE neo_address = %s ", addresses_to_whitelist)
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
    # parser = argparse.ArgumentParser()
    #
    # parser.add_argument("--disable-auto-whitelist", action="store_true", default=False,
    #                     help="Option to disable auto-whitelisting")
    #
    # args = parser.parse_args()

    # event_handler = TokenSaleEventHandler(args.disable_auto_whitelist)

    event_handler = WhitelistEventHandler()
    event_handler.run()


if __name__ == "__main__":
    main()
