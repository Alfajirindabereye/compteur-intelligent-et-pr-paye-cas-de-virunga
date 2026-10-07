CREATE TABLE `alerts` (
	`id` varchar(64) NOT NULL,
	`meterId` varchar(32) NOT NULL,
	`severity` enum('INFO','WARNING','CRITICAL') NOT NULL,
	`type` varchar(64) NOT NULL,
	`title` varchar(255) NOT NULL,
	`detail` text NOT NULL,
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	`acknowledgedAt` timestamp,
	CONSTRAINT `alerts_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `broadcastMessages` (
	`id` varchar(64) NOT NULL,
	`rawInformation` text NOT NULL,
	`generatedMessage` text NOT NULL,
	`status` enum('DRAFT','PUBLISHED') NOT NULL,
	`createdBy` int NOT NULL,
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	`publishedAt` timestamp,
	CONSTRAINT `broadcastMessages_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `meters` (
	`id` varchar(32) NOT NULL,
	`sector` varchar(128) NOT NULL,
	`location` varchar(255) NOT NULL,
	`deviceStatus` enum('ONLINE','OFFLINE') NOT NULL DEFAULT 'OFFLINE',
	`relayStatus` int NOT NULL DEFAULT 0,
	`signalStrength` int NOT NULL DEFAULT 0,
	`firmwareVersion` varchar(32) NOT NULL,
	`balanceKwh` decimal(12,3) NOT NULL DEFAULT '0',
	`updatedAt` timestamp NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT `meters_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `recharges` (
	`id` varchar(64) NOT NULL,
	`meterId` varchar(32) NOT NULL,
	`source` enum('APP_PAIEMENT','SAISIE_MANUELLE') NOT NULL,
	`status` enum('APPLIED','PENDING') NOT NULL,
	`amountCdf` decimal(14,2) NOT NULL,
	`amountUsd` decimal(14,2) NOT NULL,
	`energyKwh` decimal(12,3) NOT NULL,
	`appliedAt` timestamp NOT NULL,
	`syncedAt` timestamp NOT NULL,
	`providerReference` varchar(128),
	CONSTRAINT `recharges_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `telemetry` (
	`id` int AUTO_INCREMENT NOT NULL,
	`messageId` varchar(64) NOT NULL,
	`meterId` varchar(32) NOT NULL,
	`deviceTimestamp` timestamp NOT NULL,
	`receivedAt` timestamp NOT NULL DEFAULT (now()),
	`voltage` decimal(10,3) NOT NULL,
	`current` decimal(10,3) NOT NULL,
	`power` decimal(12,3) NOT NULL,
	`energyConsumed` decimal(12,3) NOT NULL,
	`balanceKwh` decimal(12,3) NOT NULL,
	`relayStatus` int NOT NULL,
	`signalStrength` int NOT NULL,
	`deviceStatus` enum('ONLINE','OFFLINE') NOT NULL,
	`firmwareVersion` varchar(32) NOT NULL,
	CONSTRAINT `telemetry_id` PRIMARY KEY(`id`),
	CONSTRAINT `telemetry_messageId_unique` UNIQUE(`messageId`)
);
