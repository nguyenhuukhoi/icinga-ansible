<?php
/** Expose Linuxfabrik warning/critical variables as editable Director fields. */
declare(strict_types=1);

$resources = parse_ini_file('/etc/icingaweb2/resources.ini', true, INI_SCANNER_RAW);
$resource = $resources['director_db'] ?? null;
if ($resource === null || ($resource['db'] ?? 'mysql') !== 'mysql') {
    throw new RuntimeException('A MySQL director_db resource is required');
}

$dsn = "mysql:host={$resource['host']};dbname={$resource['dbname']};charset=utf8mb4";
$db = new PDO($dsn, $resource['username'], $resource['password'], [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
]);

$rules = [
    'Linux CPU via SSH' => [
        'lfmp_cpu_warn' => 'CPU warning (%)',
        'lfmp_cpu_crit' => 'CPU critical (%)',
    ],
    'Linux RAM via SSH' => [
        'lfmp_memory_warn' => 'RAM warning (%)',
        'lfmp_memory_crit' => 'RAM critical (%)',
    ],
    'Linux Disk via SSH' => [
        'lfmp_disk_warn' => 'Disk warning (%)',
        'lfmp_disk_crit' => 'Disk critical (%)',
    ],
];
$datatype = 'Icinga\\Module\\Director\\DataType\\DataTypeNumber';
$description = 'Usage percentage. Warning must be lower than critical; accepted range is 1-100.';

$db->beginTransaction();
try {
    $findRule = $db->prepare(
        "SELECT id FROM icinga_service WHERE object_name = ? AND object_type = 'apply'"
    );
    $findField = $db->prepare('SELECT id, datatype FROM director_datafield WHERE varname = ?');
    $insertField = $db->prepare(
        'INSERT INTO director_datafield '
        . '(uuid, varname, caption, description, datatype, format) VALUES (?, ?, ?, ?, ?, NULL)'
    );
    $findLink = $db->prepare(
        'SELECT 1 FROM icinga_service_field WHERE service_id = ? AND datafield_id = ?'
    );
    $insertLink = $db->prepare(
        "INSERT INTO icinga_service_field (service_id, datafield_id, is_required, var_filter) "
        . "VALUES (?, ?, 'n', NULL)"
    );

    foreach ($rules as $ruleName => $fields) {
        $findRule->execute([$ruleName]);
        $serviceId = $findRule->fetchColumn();
        if ($serviceId === false) {
            throw new RuntimeException("Missing Director Apply Service: $ruleName");
        }
        foreach ($fields as $varname => $caption) {
            $findField->execute([$varname]);
            $field = $findField->fetch(PDO::FETCH_ASSOC);
            if ($field === false) {
                $insertField->execute([
                    random_bytes(16), $varname, $caption, $description, $datatype,
                ]);
                $fieldId = (int) $db->lastInsertId();
                echo "Created field $varname\n";
            } else {
                if ($field['datatype'] !== $datatype) {
                    throw new RuntimeException("Conflicting datatype for $varname");
                }
                $fieldId = (int) $field['id'];
            }
            $findLink->execute([(int) $serviceId, $fieldId]);
            if ($findLink->fetchColumn() === false) {
                $insertLink->execute([(int) $serviceId, $fieldId]);
                echo "Attached $varname to $ruleName\n";
            }
        }
    }
    $db->commit();
} catch (Throwable $error) {
    $db->rollBack();
    throw $error;
}
