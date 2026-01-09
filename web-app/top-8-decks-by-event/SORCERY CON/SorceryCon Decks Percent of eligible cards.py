

import json
import csv
import chardet
# Your data

t_decks = 'SorceryConDecklist.json'
cards_type = 'card_list_alpha.json'


# Open the JSON file
with open(t_decks, 'r', encoding='utf-8') as json_file:
    # Load the JSON data
    league_champ_deck_json  = json.load(json_file)
# Open the JSON file
with open(cards_type, 'r', encoding='utf-8') as json_file:
    # Load the JSON data
    cards_type_json  = json.load(json_file)
    



def find_card_percentage(card_name, decks, card_threshold):
    total_decks = len(decks)
    decks_with_card = 0
    type_counts = {'Air': 0, 'Water': 0, 'Fire': 0, 'Earth': 0}
    print(card_name, card_threshold)
    all_sites = []
    for card in cards_type_json:
        if card['Element'] == 'Site':
            all_sites.append(card['Name'])

    for deck in decks:
        sites_of_deck = []
        types_in_deck = []
        
        

        deck_name = next(iter(deck))
        #print(deck_name)
        #print(first_key)
        types = deck[deck_name].keys()
        #print(deck[first_key].keys())
        for type in types:
            for group in deck[deck_name][type]:
                if card_name == group["Name"]:
                    for card in cards_type_json:
                        if card_name == card['Name']:
                            decks_with_card += 1
                    
            
                

                    #if card_name not in all_sites:
                    #    #print(card_name)
                    #    if card_threshold in types_in_deck or card_threshold == 'Avatar':
                    #        decks_with_card += 1

                            
        #print(types_in_deck)

        #print(type_counts)
        percentage = (decks_with_card / total_decks) * 100
    return percentage






# Example usage
decks_data = league_champ_deck_json # Replace with your actual deck data
file_name = 'Percent of SorceryCon decks.csv'
card_percent = []
for card in cards_type_json:
        percentage = find_card_percentage(card['Name'], decks_data, card['Threshold'])
        card_name_to_find = card['Name']
        print(f"The percentage of decks that are eligible to have {card_name_to_find}: {percentage}%")

        card_percent.append([card['Name'],round(percentage)])
#card_name_to_find = 'Apprentice Wizard'
#percentage = find_card_percentage(card_name_to_find, decks_data, 'Air')

print(f"The percentage of decks that are eligible to have {card_name_to_find}: {percentage}%")

# Writing to CSV file
with open(file_name, 'w', newline='') as csv_file:
    csv_writer = csv.writer(csv_file)
    csv_writer.writerows(card_percent)

print(f'Data has been saved to {file_name}') 
