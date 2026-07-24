<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');

echo json_encode([
    'ok' => true,
    'service' => 'everflow-toolkit-web-php',
    'message' => 'PHP web starter — edit public/index.php',
], JSON_PRETTY_PRINT);
