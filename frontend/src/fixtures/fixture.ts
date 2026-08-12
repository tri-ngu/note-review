import type { QuestionSet } from '../types/question';

export const fixtureQuestionSet = {
  questions: [
    {
      concept: 'Ingestion and Mechanical Digestion',
      question_text: 'What is the primary role of the teeth during ingestion?',
      options: [
        'Breaking food into smaller pieces for easier swallowing',
        'Producing digestive enzymes',
        'Absorbing nutrients directly',
        'Neutralizing stomach acid',
      ],
      correct_answers: [1],
      is_select_all: false,
      explanation:
        "Teeth mechanically break food into smaller pieces, increasing the surface area available for enzymes to act on later — they don't produce enzymes or absorb nutrients themselves.",
      page_number: 1,
      source_quote:
        'As food enters the mouth, the teeth mechanically break it into smaller pieces, increasing the surface area available for enzymes to act on later in the digestive process.',
    },
    {
      concept: 'Ingestion and Mechanical Digestion',
      question_text: 'Which of the following occur during swallowing?',
      options: [
        'The epiglottis covers the trachea',
        'Saliva begins starch digestion via amylase',
        'Bile is released into the small intestine',
        'The stomach begins secreting hydrochloric acid immediately',
      ],
      correct_answers: [1, 2],
      is_select_all: true,
      explanation:
        'The epiglottis covers the trachea to prevent food from entering the airway, and salivary amylase — released earlier during chewing — is already breaking down starches. Bile release and stomach acid secretion happen later, in different stages.',
      page_number: 1,
      source_quote:
        'The epiglottis folds down over the trachea during swallowing to prevent food from entering the airway; meanwhile, salivary amylase continues breaking down starch molecules.',
    },
    {
      concept: 'Stomach and Chemical Digestion',
      question_text: 'What is the primary function of hydrochloric acid (HCl) in the stomach?',
      options: [
        'Activating pepsin and killing ingested bacteria',
        'Absorbing fats directly into the bloodstream',
        'Breaking down starches into simple sugars',
        'Neutralizing bile from the liver',
      ],
      correct_answers: [1],
      is_select_all: false,
      explanation:
        'Hydrochloric acid activates pepsinogen into pepsin, which digests proteins, and creates an acidic environment that kills most ingested bacteria.',
      page_number: 2,
      source_quote:
        "Hydrochloric acid, secreted by parietal cells in the stomach lining, activates pepsinogen into its active form, pepsin, and creates a highly acidic environment that destroys most bacteria present in food.",
    },
    {
      concept: 'Stomach and Chemical Digestion',
      question_text: 'Which of the following are true about pepsin?',
      options: [
        'It is a protein-digesting enzyme',
        'It works best in an acidic environment',
        'It is produced in an inactive form called pepsinogen',
        'It begins breaking proteins into smaller peptides',
      ],
      correct_answers: [1, 2, 3, 4],
      is_select_all: true,
      explanation:
        'All four statements accurately describe pepsin: it digests proteins, requires an acidic environment to function, starts as inactive pepsinogen, and breaks proteins down into smaller peptide chains.',
      page_number: 2,
      source_quote:
        "Pepsin, a protein-digesting enzyme, is secreted as inactive pepsinogen and only becomes active in the stomach's acidic environment, where it begins cleaving proteins into smaller peptide fragments.",
    },
    {
      concept: 'Small Intestine and Absorption',
      question_text:
        "A student is studying how the small intestine maximizes nutrient absorption despite its limited length compared to the large intestine; which structural feature is most directly responsible for dramatically increasing the intestine's internal surface area available for absorbing nutrients into the bloodstream?",
      options: [
        'Finger-like projections called villi (and microvilli) lining the intestinal wall',
        'The thick muscular layer surrounding the intestine',
        'The presence of gut bacteria in the intestinal lumen',
        "The intestine's overall length alone",
      ],
      correct_answers: [1],
      is_select_all: false,
      explanation:
        "Villi, and the even smaller microvilli covering them, dramatically increase the small intestine's internal surface area — far more than length alone could achieve — which is what allows efficient nutrient absorption despite the organ's limited length relative to the large intestine.",
      page_number: 3,
      source_quote:
        'The inner wall of the small intestine is covered in millions of finger-like projections called villi, each covered in even smaller microvilli, which together dramatically increase the surface area available for nutrient absorption.',
    },
    {
      concept: 'Small Intestine and Absorption',
      question_text: 'Which of the following aid digestion within the small intestine?',
      options: [
        'Bile from the liver, stored in the gallbladder',
        'Pancreatic enzymes released into the duodenum',
        'Villi that increase absorptive surface area',
        'Hydrochloric acid secreted by the stomach lining',
      ],
      correct_answers: [1, 2, 3],
      is_select_all: true,
      explanation:
        'Bile emulsifies fats, pancreatic enzymes break down carbohydrates, proteins, and fats, and villi absorb the resulting nutrients — all directly aiding small-intestine digestion. Hydrochloric acid is a stomach-specific secretion, not part of small intestine digestion.',
      page_number: 3,
      source_quote:
        'Within the duodenum, bile released from the gallbladder emulsifies fats while pancreatic enzymes continue breaking down carbohydrates, proteins, and fats; the resulting nutrients are then absorbed through the villi lining the intestinal wall.',
    },
    {
      concept: 'Large Intestine and Elimination',
      question_text: 'What is the primary function of the large intestine?',
      options: [
        'Absorbing remaining water and electrolytes from digested material',
        'Producing digestive enzymes for protein breakdown',
        'Absorbing the majority of nutrients from food',
        'Neutralizing stomach acid before it reaches the small intestine',
      ],
      correct_answers: [1],
      is_select_all: false,
      explanation:
        "The large intestine's primary role is absorbing remaining water and electrolytes from indigestible material, compacting it into feces — most nutrient absorption already happened in the small intestine.",
      page_number: 4,
      source_quote:
        "By the time digested material reaches the large intestine, most nutrients have already been absorbed; the large intestine's main role is reabsorbing remaining water and electrolytes, compacting waste into feces.",
    },
    {
      concept: 'Large Intestine and Elimination',
      question_text: 'Which of the following statements about gut bacteria in the large intestine is correct?',
      options: [
        'They help break down some remaining undigested material and produce certain vitamins',
        'They are harmful and the immune system actively eliminates all of them',
        'They primarily digest proteins the stomach failed to break down',
        'They convert absorbed nutrients directly into muscle tissue',
      ],
      correct_answers: [1],
      is_select_all: true,
      explanation:
        'Only the first statement is accurate — gut bacteria in the large intestine ferment remaining undigested material and synthesize certain vitamins, a beneficial symbiotic relationship, not something the immune system eliminates.',
      page_number: 4,
      source_quote:
        'Beneficial bacteria residing in the large intestine ferment remaining undigested carbohydrates and synthesize certain vitamins, including vitamin K, in a symbiotic relationship with the host.',
    },
  ],
} satisfies QuestionSet;
