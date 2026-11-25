shaarav@Shaaravs-MacBook-Air Data_Analytics % >....                                                                                                                                                            

    git -C "$WORKDIR" add -A -- "${ROOT_FILES[@]}"

    # Also stage the bootstrap .gitignore if source provided one
    if [ -f "$SOURCE/.gitignore" ]; then
        git -C "$WORKDIR" add .gitignore
    fi

    git -C "$WORKDIR" commit -m "Add root-level project files"
    git -C "$WORKDIR" push -u origin "$BRANCH"

    ROOT_PR_URL=$(
        cd "$WORKDIR"
        gh pr create \
            --repo "$REPO" \
            --base main \
            --head "$BRANCH" \
            --title "Add root-level project files" \
            --body "Adds root-level presentation and project files."
    )

    echo "PR CREATED: $ROOT_PR_URL"

    git -C "$WORKDIR" switch main
fi

# ==========================================
# STEP 4: CREATE FOLDER PRs
# ==========================================

create_pr "import/pycode" "Add Python analytics projects" "PyCode"

create_pr "import/raw-data" "Add raw datasets" "raw_data"

create_pr "import/sql-input" "Add SQL input files" "SQL_Input"

create_pr "import/sql-output" "Add SQL output files" "SQL_Output"

# ==========================================
# STEP 5: FINISH
# ==========================================

echo ""
echo "=========================================="
echo "ALL PULL REQUESTS PROCESSED"
echo "=========================================="

echo ""
echo "Visit your repository:"
echo "https://github.com/$REPO"

echo ""
echo "View all pull requests:"
echo "https://github.com/$REPO/pulls"

echo ""
echo "Your original local project was not modified."

zsh: event not found: /bin/bash
shaarav@Shaaravs-MacBook-Air Data_Analytics % >....                                                                                                                                                            
    ! -name ".DS_Store" -print0
)                                  
shaarav@Shaaravs-MacBook-Air Data_Analytics % >....                                                                                                                                                            
    # Also stage the bootstrap .gitignore if source provided one
    if [ -f "$SOURCE/.gitignore" ]; then
        git -C "$WORKDIR" add .gitignore
    fi                                                

    git -C "$WORKDIR" commit -m "Add root-level project files"
    git -C "$WORKDIR" push -u origin "$BRANCH"

    ROOT_PR_URL=$(                                         
        cd "$WORKDIR"
        gh pr create \            
            --repo "$REPO" \             
            --base main \ 
            --head "$BRANCH" \
            --title "Add root-level project files" \
            --body "Adds root-level presentation and project files."
    )

    echo "PR CREATED: $ROOT_PR_URL"               
    
    git -C "$WORKDIR" switch main                                                
fi

# ==========================================         
# STEP 4: CREATE FOLDER PRs                         
# ==========================================                   
    
create_pr "import/pycode" "Add Python analytics projects" "PyCode"
    
create_pr "import/raw-data" "Add raw datasets" "raw_data"

create_pr "import/sql-input" "Add SQL input files" "SQL_Input"

create_pr "import/sql-output" "Add SQL output files" "SQL_Output"
        
# ==========================================
# STEP 5: FINISH
# ==========================================  

echo ""                   
echo "=========================================="         
echo "ALL PULL REQUESTS PROCESSED"             
echo "=========================================="

echo ""                                    
echo "Visit your repository:"        
echo "https://github.com/$REPO"            
    
echo ""
echo "View all pull requests:"
echo "https://github.com/$REPO/pulls"            

echo ""
echo "Your original local project was not modified."                                                                                                                                                     

zsh: event not found: /bin/bash
shaarav@Shaaravs-MacBook-Air Data_Analytics % 

