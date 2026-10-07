CREATE TABLE `budgetSettings` (
	`meterId` varchar(32) NOT NULL,
	`limitKwh` decimal(12,3) NOT NULL,
	`warningPercentage` int NOT NULL DEFAULT 80,
	`updatedAt` timestamp NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT `budgetSettings_meterId` PRIMARY KEY(`meterId`)
);
--> statement-breakpoint
CREATE TABLE `meterTokens` (
	`id` int AUTO_INCREMENT NOT NULL,
	`meterId` varchar(32) NOT NULL,
	`sequence` int NOT NULL,
	`tokenDigest` varchar(128) NOT NULL,
	`energyKwh` decimal(12,3) NOT NULL,
	`appliedAt` timestamp,
	`syncedAt` timestamp,
	`used` int NOT NULL DEFAULT 0,
	CONSTRAINT `meterTokens_id` PRIMARY KEY(`id`),
	CONSTRAINT `meterTokens_tokenDigest_unique` UNIQUE(`tokenDigest`)
);
--> statement-breakpoint
CREATE TABLE `sectors` (
	`id` varchar(32) NOT NULL,
	`name` varchar(128) NOT NULL,
	`territory` varchar(128) NOT NULL,
	CONSTRAINT `sectors_id` PRIMARY KEY(`id`),
	CONSTRAINT `sectors_name_unique` UNIQUE(`name`)
);
