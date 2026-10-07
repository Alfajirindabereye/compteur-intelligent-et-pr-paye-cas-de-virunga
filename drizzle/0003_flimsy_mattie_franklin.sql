CREATE TABLE `paymentEvents` (
	`id` varchar(128) NOT NULL,
	`provider` varchar(32) NOT NULL,
	`status` varchar(32) NOT NULL,
	`payload` text NOT NULL,
	`receivedAt` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `paymentEvents_id` PRIMARY KEY(`id`)
);
