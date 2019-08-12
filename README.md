# neo_token_crowdsale_whitelist_script
Crowdsale whitelist handler with database

How to use the script:
clone repository into a nep-python docker container (or environment)

you need to install mariadb:
```
apt-get install -y mariadb-server mariadb-client
```

# MariaDB & nvm Database
restart the service
```
service mysql restart
```
start mysql/mariadb shell
```
mysql
```
create database & user:
```
create database nvm;
CREATE USER 'nvmuser'@'localhost' IDENTIFIED BY 'nvmnvmnvmnvm';
```
create the table for whitelisting addresses
```
CREATE TABLE `NvmUser` (
	`crowdsale_register` BOOLEAN NOT NULL DEFAULT 0 COMMENT 'neo address is crowdsale registered',
	`id` INT NOT NULL AUTO_INCREMENT COMMENT 'primary key',
	`neo_address` VARCHAR(100),
	PRIMARY KEY (`id`)
);
```

if NEO addresses are inserted into the DB they get the value for the field `crowdsale_register` as 0
and are selected for whitelisting
after the whitelisitng they ar marked with 1

execute: 
```
pip install -U setuptools pip wheel
pip install -e .
```

to run the script:
```
python3 whitelistEventHandler.py
```

Script will ask for the wallet password at the beginning

wallets can be configured in config/network-wallets.json

# Troubleshooting

## if you get a 
leveldb unavailable, you may already be running this process: b'IO error: lock /root/.neopython/Chains/SC234/LOCK: Resource temporarily unavailable' error
either np-prompt is running or you need to delete the /root/.neopython/Chains/SC234/LOCK file

