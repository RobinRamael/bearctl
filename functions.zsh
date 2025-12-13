

run_eww() {
    $EWW_EXECUTABLE -c $EWW_CONFIG kill
    $EWW_EXECUTABLE -c $EWW_CONFIG daemon
    $EWW_EXECUTABLE -c $EWW_CONFIG open top-bar
    $EWW_EXECUTABLE -c $EWW_CONFIG open bottom-bar
    $EWW_EXECUTABLE -c $EWW_CONFIG logs
}

