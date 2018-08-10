var=1
while read -r file; do
 cp "$file" "messages_tmp/$var" 
 var=$((var+1))	
done < "Facebookfileslist"
