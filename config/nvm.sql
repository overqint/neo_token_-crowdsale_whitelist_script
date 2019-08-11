create database nvm;

CREATE USER 'nvmuser'@'localhost' IDENTIFIED BY 'nvmnvmnvmnvm';

GRANT ALL PRIVILEGES ON *.* TO 'nvmuser'@'localhost';

CREATE TABLE `NvmUser` (
	`crowdsale_register` BOOLEAN NOT NULL DEFAULT 0 COMMENT 'neo address is crowdsale registered',
	`id` INT NOT NULL AUTO_INCREMENT COMMENT 'primary key',
	`neo_address` VARCHAR(100),
	PRIMARY KEY (`id`)
);

#privnet wallet
insert into NvmUser (neo_address) VALUES ('AK2nJJpJr6o664CWJKi1QRXjqeic2zRp8y');
#nvm1 wallet
insert into NvmUser (neo_address) VALUES ('AUdrw6TSf3uwvMBK6cNyrRQNfWrdHnXjiF');
#nvm2 wallet
insert into NvmUser (neo_address) VALUES ('AL1bpyJ9f9PbHe6VZoyHGj1QY5xzuCSVuq');

