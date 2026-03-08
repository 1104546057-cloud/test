CREATE TABLE IF NOT EXISTS InspectArea (
  AreaId   INT AUTO_INCREMENT PRIMARY KEY,
  AreaName VARCHAR(100) NOT NULL,
  AreaCode VARCHAR(100) NOT NULL,
  AreaDesc VARCHAR(255),
  Status   TINYINT DEFAULT 1,
  Remark   VARCHAR(255),
  UNIQUE KEY uk_area_code (AreaCode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS InspectPoint (
  PointId   INT AUTO_INCREMENT PRIMARY KEY,
  AreaId    INT NOT NULL,
  PointName VARCHAR(100) NOT NULL,
  PointCode VARCHAR(100) NOT NULL,
  PointType INT DEFAULT 0,
  Longitude DECIMAL(10,6),
  Latitude  DECIMAL(10,6),
  Remark    VARCHAR(255),
  Status    TINYINT DEFAULT 1,
  UNIQUE KEY uk_point_code (PointCode),
  KEY idx_point_area (AreaId),
  CONSTRAINT fk_point_area FOREIGN KEY (AreaId) REFERENCES InspectArea(AreaId)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS InspectRoute (
  RouteId     INT AUTO_INCREMENT PRIMARY KEY,
  AreaId      INT NOT NULL,
  RouteName   VARCHAR(100) NOT NULL,
  RouteCode   VARCHAR(100) NOT NULL,
  PlanType    INT DEFAULT 0,
  Status      TINYINT DEFAULT 1,
  PointCount  INT DEFAULT 0,
  PathLength  DECIMAL(10,2) DEFAULT 0,
  InsDuration DECIMAL(10,2) DEFAULT 0,
  Remark      VARCHAR(255),
  UNIQUE KEY uk_route_code (RouteCode),
  KEY idx_route_area (AreaId),
  CONSTRAINT fk_route_area FOREIGN KEY (AreaId) REFERENCES InspectArea(AreaId)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
