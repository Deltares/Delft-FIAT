#!/usr/bin/env bash

set -e

BASE_URL="https://deltares.github.io/Delft-FIAT"
CUR_DIR="$(dirname "$(realpath "$0")")"
ROOT_DIR="$(realpath "$CUR_DIR")"

VERSIONS_JSON="$ROOT_DIR/versions.json"
SWITCHER_JSON="$ROOT_DIR/switcher.json"

check() {
    local new_versions=()
    local existing_versions
    existing_versions=$(jq -r '.[].version' "$VERSIONS_JSON")

    # Find directories like v1.2.3 or v1.2.3rc1
    mapfile -t dir_versions < <(find "$ROOT_DIR" -maxdepth 1 -type d -printf "%f\n" | grep -E '^v[0-9]+\.[0-9]+(\.[0-9]+)?([a-zA-Z0-9]+)?$' | sed 's/^v//')

    for dir in "${dir_versions[@]}"; do
        if ! grep -qx "$dir" <<< "$existing_versions"; then
            new_versions+=("$dir")
        fi
    done

    if [ ${#new_versions[@]} -eq 0 ]; then
        echo "No new versions found."
        return 1
    fi

    # Combine existing and new versions
    mapfile -t all_versions < <(printf "%s\n" $existing_versions "${new_versions[@]}" | sort -u)

    # Build JSON array
    {
        echo "["
        for i in "${!all_versions[@]}"; do
            v="${all_versions[$i]}"
            printf '  { "name": "v%s", "version": "%s" }' "$v" "$v"
            if [ "$i" -lt "$((${#all_versions[@]} - 1))" ]; then
                echo ","
            else
                echo
            fi
        done
        echo "]"
    } > "$VERSIONS_JSON.tmp" && mv "$VERSIONS_JSON.tmp" "$VERSIONS_JSON"

    echo "${dir_versions[@]}"
}

add() {
    local new_versions=("$@")
    local updated=false

    # Extract special entries
    mapfile -t special_entries < <(jq -c '.[] | select(.version == "latest" or .version == "stable" or .version == "dev")' "$SWITCHER_JSON")

    # Extract versioned entries
    mapfile -t version_entries < <(jq -c '.[] | select(.version != "latest" and .version != "stable" and .version != "dev")' "$SWITCHER_JSON")

    # Extract existing version strings
    mapfile -t existing_versions < <(printf "%s\n" "${version_entries[@]}" | jq -r '.version')

    # Add new versions if not already present
    for v in "${new_versions[@]}"; do
        if ! printf "%s\n" "${existing_versions[@]}" | grep -qx "$v"; then
            version_entries+=("{\"name\": \"v$v\", \"version\": \"$v\", \"href\": \"$BASE_URL/v$v/\"}")
            updated=true
        fi
    done

    if [ "$updated" = false ]; then
        echo "New documentation folder(s) already existed in 'switcher.json'!"
        return 1
    fi

    # Sort all versions
    # Group versions by base version
    declare -A version_groups


    # Extract version strings from JSON entries
    mapfile -t version_strings < <(printf "%s\n" "${version_entries[@]}" | jq -r '.version')

    for v in "${version_strings[@]}"; do
    # Extract base version (e.g. 0.2.1 from 0.2.1rc2)
    base="${v%%[a-zA-Z]*}"
    version_groups["$base"]+="$v"$'\n'
    done

    # Sort base versions descending
    mapfile -t sorted_bases < <(printf "%s\n" "${!version_groups[@]}" | sort -r -V)

    # Final sorted list
    sorted_versions=()

    for base in "${sorted_bases[@]}"; do
    # Sort group: full release first, then pre-releases descending
    mapfile -t group < <(printf "%s\n" ${version_groups[$base]} | sort -V)

    # Separate full release and pre-releases
    full=""
    pre=()
    for v in "${group[@]}"; do
        if [[ "$v" =~ [a-zA-Z] ]]; then
        pre+=("$v")
        else
        full="$v"
        fi
    done

    # Add full release first, then pre-releases in reverse order
    if [[ -n "$full" ]]; then
        sorted_versions+=("$full")
    fi
    if [[ ${#pre[@]} -gt 0 ]]; then
        mapfile -t reversed_pre < <(printf "%s\n" "${pre[@]}" | sort -r -V)
        sorted_versions+=("${reversed_pre[@]}")
    fi
    done
	
    # Find the highest non-release-candidate version
    for ((i=0; i<${#sorted_versions[@]}; i++)); do
        v="${sorted_versions[$i]}"
        if [[ ! "$v" =~ [a-zA-Z] ]]; then
            stable="$v"
            unset 'sorted_versions[i]'
            break
        fi
    done

    # Reverse the remaining versions
    # mapfile -t reversed_versions < <(printf "%s\n" "${sorted_versions[@]}" | tac)

    # Rebuild sorted version entries
    sorted_entries=()
    for v in "${sorted_versions[@]}"; do
        sorted_entries+=("{\"name\": \"v$v\", \"version\": \"$v\", \"href\": \"$BASE_URL/v$v/\"}")
    done

    # Combine all entries into valid JSON
    {
        echo "["
        for entry in "${special_entries[@]}"; do
            echo "  $entry,"
        done
        for i in "${!sorted_entries[@]}"; do
            echo -n "  ${sorted_entries[$i]}"
            if [ "$i" -lt "$((${#sorted_entries[@]} - 1))" ]; then
                echo ","
            else
                echo
            fi
        done
        echo "]"
    } > "$SWITCHER_JSON.tmp" && mv "$SWITCHER_JSON.tmp" "$SWITCHER_JSON"

    # Determine new stable version
    echo "v$stable"
}

main() {
    if ! new_versions=$(check); then
        echo "No new documentation folders found!"
        exit 1
    fi

    IFS=' ' read -r -a new_versions_array <<< "$new_versions"

    if ! stable_version=$(add "${new_versions_array[@]}"); then
        echo "New documentation folder(s) already existed in 'switcher.json'!"
        exit 1
    fi

    echo "Current stable version set to: ${stable_version}"
    echo "NEW_STABLE_VERSION=$stable_version" >> "$GITHUB_ENV"
}

main
